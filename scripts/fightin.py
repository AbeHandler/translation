#!/usr/bin/env python
"""
Fightin' Words (src/fightin) between English and Chinese AI coverage: which phrases (or words) each emphasises more,
with Chinese units put on the English vocabulary by a multilingual embedding (each Chinese unit -> its nearest
English unit, src/fightin/concepts.py). One run does everything, for every selection in -selections
(config/fightin_selections.tsv: the whole sample, documents naming OpenAI, naming Anthropic ...).

Outputs in results/fightin/<experiment>/, the experiment named after the sample size (en_vs_zh_ai_20k), so samples
never collide; words and phrases share a sample and their files carry the unit (_ngrams2-3), each selection's
comparison its name (_openai):
    sample   -n AI documents per language, random files and row groups, at most -per-file from each file:
                 Chinese: the site crawls (data/interim/site_crawls/*/html), Chinese and about AI (primary_sources
                 chinese_ai_page); sampled first, as the smaller pool
                 English: CC-NEWS pages (data/interim/cc_html), English, saying "AI" at least twice, dated by crawl
             main text by readability                                        -> docs.parquet
    words    the units counted (src/fightin/units.py): with -ngrams 2-3 (default) phrases of 2-3 words with content
             words at both ends, with -ngrams 1 words; English by regex, Chinese by jieba with the AI terms
                                                                             -> units_<unit>.parquet
    embed    units in at least -min-df documents of their language (at most -max-vocab), by LaBSE
                                                                             -> index_<unit>.npz
    compare  for each selection: its document ids (pattern on title and text, dates, or an ids file)
                                                                             -> selections/<name>.txt
             Chinese units -> English concepts (cosine >= -threshold); concepts in -stopwords left out
                                                                             -> concepts_<unit>_<name>.tsv
             Fightin' Words over concepts used in both languages, English (i) vs Chinese (j) documents of the
             selection: log-odds with an informative Dirichlet prior (-alpha0; background: the whole sample), z
                                                                             -> fightin_<unit>_<name>.tsv
             the funnel plot (font: bash scripts/fetch_cjk_font.sh)          -> funnel_<unit>_<name>.png
             a selection with fewer than -min-docs documents in a language is reported, and the run then fails
             once the others are done
    all      the steps in order: sample is reused if docs.parquet exists, embed if index has exactly the units;
             the rest always rerun, so after any change one run redoes what's needed
    flush    deletes results/fightin/<experiment>/

Run as a module from the repo root (normally: sbatch scripts/slurm/fightin.slurm):
    python -m scripts.fightin -step all                    # 20k documents per language, phrases, every selection
    python -m scripts.fightin -step all -ngrams 1          # words, on the same sample
"""
import argparse
import glob
import os
import random
import shutil
from collections import Counter, defaultdict

import numpy as np
import pandas as pd
import pyarrow.parquet as pq

from config.paths import (CC_HTML_DIR, FIGHTIN_SELECTIONS_PATH, FONTS_DIR, REPO_ROOT, SITE_CRAWLS_DIR,
                          STOPWORDS_EN_PATH)
from src.ai_mentions import mentions_ai, mentions_ai_html
from src.dispersion.tokens import tokens
from src.external_links import registered_domain
from src.fightin.concepts import concept_counts, pivot_concepts, read_stopwords
from src.fightin.counts import GroupCounts
from src.fightin.embeddings.backends import from_encoder
from src.fightin.embeddings.index import VectorIndex
from src.fightin.measures import log_odds_dirichlet
from src.fightin.plot import chinese_form, funnel_plot_tsv
from src.fightin.select import doc_id, read_ids, select_ids, write_ids
from src.fightin.units import parse_ns, units
from src.primary_sources import chinese_ai_page
from src.source_texts import html_text

NAME = 'fightin'
STEPS = ('sample', 'words', 'embed', 'compare')
MIN_TEXT_CHARS = 300


def parse_args():
    parser = argparse.ArgumentParser(description="Fightin' Words between English and Chinese AI coverage")
    parser.add_argument('-step', default='all', choices=STEPS + ('all', 'flush'))
    parser.add_argument('-n', type=int, default=20000, help='documents per language')
    parser.add_argument('-experiment-name', default=None, help='default: en_vs_zh_ai_<n in thousands>k')
    parser.add_argument('-per-file', type=int, default=100, help='at most this many documents from one file')
    parser.add_argument('-ngrams', default='2-3', help="unit: '2-3' = phrases of 2 to 3 words; 1 = words")
    parser.add_argument('-selections', default=str(FIGHTIN_SELECTIONS_PATH), help='the comparisons to make')
    parser.add_argument('-min-df', type=int, default=5, help='units in fewer documents of their language: no vector')
    parser.add_argument('-max-vocab', type=int, default=30000, help='embed at most this many units per language')
    parser.add_argument('-threshold', type=float, default=None,
                        help='Chinese unit -> English concept at this cosine (default 0.6 for words, 0.7 phrases)')
    parser.add_argument('-alpha0', type=float, default=1000, help="the prior's size (the paper's alpha_0)")
    parser.add_argument('-stopwords', default=str(STOPWORDS_EN_PATH), help="concepts left out; '' keeps all")
    parser.add_argument('-min-docs', type=int, default=30, help='a selection needs this many documents per language')
    parser.add_argument('-seed', type=int, default=0)
    parser.add_argument('-cc-html-dir', default=str(CC_HTML_DIR))
    parser.add_argument('-crawls-dir', default=str(SITE_CRAWLS_DIR))
    args = parser.parse_args()
    size = f'{args.n // 1000}k' if args.n % 1000 == 0 else str(args.n)
    args.experiment_name = args.experiment_name or f'en_vs_zh_ai_{size}'
    args.out = os.path.join(REPO_ROOT, 'results', NAME, args.experiment_name)
    args.ns = parse_ns(args.ngrams)
    args.unit_name = 'words' if args.ns == (1,) else 'phrases'
    args.unit = 'words' if args.ns == (1,) else f'ngrams{args.ngrams}'
    args.threshold = args.threshold or (0.6 if args.ns == (1,) else 0.7)
    args.stop = read_stopwords(args.stopwords) if args.stopwords else frozenset()
    return args


def path(args, name, selection=None):
    """A file of the experiment: docs.parquet is shared; the rest carry the unit (units_ngrams2-3.parquet), a
    comparison's files also the selection (fightin_ngrams2-3_openai.tsv)."""
    if name == 'docs.parquet':
        return os.path.join(args.out, name)
    stem, ext = os.path.splitext(name)
    return os.path.join(args.out, f"{stem}_{args.unit}{f'_{selection}' if selection else ''}{ext}")


def read_selections(path_):
    """[{name, pattern, from, to, ids}] of a selections file (tab-separated, # comments)."""
    table = pd.read_csv(path_, sep='\t', comment='#', dtype=str, keep_default_na=False)
    for column in ('pattern', 'from', 'to', 'ids'):
        if column not in table:
            table[column] = ''
    if table['name'].duplicated().any():
        raise SystemExit(f'{path_}: duplicate selection names')
    return table.to_dict('records')


def english_doc(row):
    """{title, text, date} of an English CC-NEWS page about AI, else None."""
    if not (row.get('language') or '').startswith('en') or mentions_ai_html(row['html'])[0] < 2:
        return None
    title, text = html_text(row['html'].decode('utf-8', errors='replace'))
    if len(text) < MIN_TEXT_CHARS or not mentions_ai(text):
        return None
    return {'title': title, 'text': text, 'date': (row.get('warc_date') or '')[:10]}   # crawl date, near publication


def chinese_doc(row):
    """{title, text, date} of a Chinese crawled page about AI, else None."""
    page = chinese_ai_page(row, '9999-12-31')
    if page is None:
        return None
    title, text = html_text(page[0])
    return {'title': title, 'text': text, 'date': page[1]} if len(text) >= MIN_TEXT_CHARS else None


def sample_language(paths, read_doc, lang, args, rng, columns=('url', 'language', 'html')):
    """Up to args.n documents: files in random order, each file's row groups in random order, at most
    args.per_file documents from one file."""
    docs = []
    rng.shuffle(paths)
    for n, file in enumerate(paths, 1):
        try:
            reader = pq.ParquetFile(file)
            groups = list(range(reader.num_row_groups))
            rng.shuffle(groups)
            found = 0
            for g in groups:
                for row in reader.read_row_group(g, columns=list(columns)).to_pylist():
                    try:
                        doc = read_doc(row)
                    except Exception:     # one unparseable page shouldn't stop the sample
                        continue
                    if doc:
                        docs.append({'lang': lang, 'url': row['url'], 'outlet': registered_domain(row['url']),
                                     'date': doc.get('date', ''), 'title': doc['title'], 'text': doc['text']})
                        found += 1
                    if found >= args.per_file or len(docs) >= args.n:
                        break
                if found >= args.per_file or len(docs) >= args.n:
                    break
        except Exception as e:
            print(f'  skipped {file}: {e}', flush=True)
        if n % 20 == 0 or len(docs) >= args.n:
            print(f'  {lang}: {n} files read, {len(docs)}/{args.n} documents', flush=True)
        if len(docs) >= args.n:
            break
    if len(docs) < args.n:
        raise SystemExit(f'only {len(docs)} {lang} documents found in {len(paths)} files; lower -n '
                         '(N), or raise -per-file (PER_FILE)')
    return docs


def sample_step(args):
    rng = random.Random(args.seed)
    # Chinese first: the crawls are the smaller pool, so a too-large -n fails before the English hours are spent
    zh = sample_language(glob.glob(os.path.join(args.crawls_dir, '*', 'html', '*.parquet')), chinese_doc, 'zh',
                         args, rng)
    en = sample_language(glob.glob(os.path.join(args.cc_html_dir, '*.parquet')), english_doc, 'en', args, rng,
                         columns=('url', 'language', 'warc_date', 'html'))
    docs = pd.DataFrame(en + zh)
    docs.to_parquet(path(args, 'docs.parquet'))
    print(docs.groupby('lang').agg(docs=('url', 'size'), outlets=('outlet', 'nunique'),
                                   median_chars=('text', lambda t: int(t.str.len().median()))))


def doc_units(text, lang, args):
    return units([t for t, _, _ in tokens(text, lang)], lang, args.ns, args.stop)


def words_step(args):
    docs = pd.read_parquet(path(args, 'docs.parquet'))
    rows = []
    for lang, group in docs.groupby('lang'):
        count, df = Counter(), Counter()
        for text in group['text']:
            found = doc_units(text, lang, args)
            count.update(found)
            df.update(set(found))
        rows += [{'lang': lang, 'word': w, 'count': c, 'df': df[w]} for w, c in count.items()]
    words = pd.DataFrame(rows)
    words.to_parquet(path(args, 'units.parquet'))
    for lang, group in words.groupby('lang'):
        print(f'{lang}: {len(group)} {args.unit_name}, {group["count"].sum()} occurrences, '
              f'{(group["df"] >= args.min_df).sum()} in {args.min_df}+ documents')


def embed_step(args):
    from src.dispersion.encoders import labse
    words = pd.read_parquet(path(args, 'units.parquet'))
    wanted = {lang: group.sort_values('df', ascending=False).head(args.max_vocab)['word'].tolist()
              for lang, group in words[words['df'] >= args.min_df].groupby('lang')}
    if os.path.exists(path(args, 'index.npz')):
        old = VectorIndex.load(path(args, 'index.npz'))
        if set(old.position) == {(lang, w) for lang, ws in wanted.items() for w in ws}:
            print(f"{path(args, 'index.npz')} already has these {args.unit_name}, reused")
            return
    encode = labse()
    index = VectorIndex()
    for lang, ws in wanted.items():
        print(f'embedding {len(ws)} {lang} {args.unit_name}', flush=True)
        index.add(*from_encoder(ws, encode, say=lambda line: print(line, flush=True)), lang=lang)
    index.save(path(args, 'index.npz'))


def selection_ids(docs, selection):
    if selection['name'] == 'all':
        return [doc_id(u) for u in docs['url']]
    if selection['ids']:
        return sorted(read_ids(selection['ids']))
    return select_ids(docs, selection['pattern'] or None, selection['from'] or None, selection['to'] or None)


def fight(args, docs, mapping, pool, name):
    """One comparison: the English vs Chinese documents in docs -> concepts, fightin and funnel files."""
    zh_docs, en_docs = docs.loc[docs['lang'] == 'zh', 'units'], docs.loc[docs['lang'] == 'en', 'units']
    zh_counts, en_counts = concept_counts(zh_docs, mapping, args.stop), concept_counts(en_docs, None, args.stop)
    zh_unit_counts = Counter(w for d in zh_docs for w in d)
    members = defaultdict(Counter)       # concept -> its Chinese units, by count
    for w, n in zh_unit_counts.items():
        members[mapping[w][0]][w] = n
    concepts = pd.DataFrame([{'word': w, 'concept': c, 'similarity': round(s, 3), 'count': zh_unit_counts[w]}
                             for w, (c, s) in mapping.items() if zh_unit_counts[w]])
    concepts.sort_values('count', ascending=False).to_csv(path(args, 'concepts.tsv', name), sep='\t', index=False)

    shared = sorted(c for c in en_counts if zh_counts.get(c))
    counts = GroupCounts(shared, np.array([en_counts[c] for c in shared], float),
                         np.array([zh_counts[c] for c in shared], float), np.array([pool[c] for c in shared], float))
    lo = log_odds_dirichlet(counts, alpha0=args.alpha0)
    zh_forms = {c: ' '.join(w for w, _ in members[c].most_common(3)) for c in shared}
    labels = [f'{c} / {chinese_form(zh_forms[c])}' if chinese_form(zh_forms[c]) else c for c in shared]
    table = pd.DataFrame({'concept': shared, 'zh_forms': [zh_forms[c] for c in shared], 'label': labels,
                          'en': counts.i, 'zh': counts.j, 'delta': lo.delta, 'z': lo.z})
    table = table.sort_values('z', ascending=False)
    table.to_csv(path(args, 'fightin.tsv', name), sep='\t', index=False, float_format='%.4g')
    funnel_plot_tsv(path(args, 'fightin.tsv', name), path(args, 'funnel.png', name),
                    font_paths=sorted(FONTS_DIR.glob('*.[ot]tf')),
                    title=f"Fightin' Words: English vs Chinese AI ({args.experiment_name}, {args.unit_name}, {name})")
    tail = table.tail(10)[::-1]
    print(f'  {len(shared)} concepts used in both languages')
    print('  most English:', ', '.join(table['concept'].head(10)))
    chinese = [f'{c} {chinese_form(f)}'.strip() for c, f in zip(tail['concept'], tail['zh_forms'])]
    print('  most Chinese:', ', '.join(chinese))
    print(f"  -> {path(args, 'fightin.tsv', name)}, {path(args, 'funnel.png', name)}")


def compare_step(args):
    """Every selection: its ids, then the comparison. Units, the mapping and the prior's background (the whole
    sample) are worked out once."""
    docs = pd.read_parquet(path(args, 'docs.parquet'))
    index = VectorIndex.load(path(args, 'index.npz'))
    print(f'{args.unit_name} of {len(docs)} documents', flush=True)
    docs['units'] = [doc_units(t, lang, args) for t, lang in zip(docs['text'], docs['lang'])]
    docs['id'] = docs['url'].map(doc_id)
    mapping = pivot_concepts(index, sorted({w for d in docs.loc[docs['lang'] == 'zh', 'units'] for w in d}),
                             args.threshold)
    mapped = sum(1 for c, s in mapping.values() if s >= args.threshold)
    print(f'{len(mapping)} Chinese {args.unit_name}, {mapped} mapped to an English one (cosine >= {args.threshold})')
    pool = concept_counts(docs.loc[docs['lang'] == 'zh', 'units'], mapping, args.stop) + \
        concept_counts(docs.loc[docs['lang'] == 'en', 'units'], None, args.stop)
    os.makedirs(os.path.join(args.out, 'selections'), exist_ok=True)
    too_small = []
    for selection in read_selections(args.selections):
        name = selection['name']
        ids = selection_ids(docs, selection)
        write_ids(ids, os.path.join(args.out, 'selections', f'{name}.txt'))
        chosen = docs[docs['id'].isin(set(ids))]
        per_lang = chosen['lang'].value_counts().reindex(['en', 'zh'], fill_value=0)
        print(f"\n--- {name}: {per_lang['en']} English, {per_lang['zh']} Chinese documents", flush=True)
        if per_lang.min() < args.min_docs:
            print(f'  fewer than {args.min_docs} in a language: skipped')
            too_small.append(name)
            continue
        fight(args, chosen, mapping, pool, name)
    print(f'\nSpot checks:\n  ls {args.out}\n  head -30 {path(args, "fightin.tsv", "all")} | column -t -s $\'\\t\'')
    if too_small:
        raise SystemExit(f'too few documents for {", ".join(too_small)} (the others are done): loosen the pattern, '
                         'or sample more (N)')


def flush_step(args):
    if os.path.isdir(args.out):
        shutil.rmtree(args.out)
        print(f'deleted {args.out}')


def main():
    args = parse_args()
    if args.step == 'flush':
        return flush_step(args)
    os.makedirs(args.out, exist_ok=True)
    print(f'experiment {args.experiment_name}: {args.n} documents per language, {args.unit_name} -> {args.out}')
    run = {'sample': sample_step, 'words': words_step, 'embed': embed_step, 'compare': compare_step}
    for step in STEPS if args.step == 'all' else (args.step,):
        if args.step == 'all' and step == 'sample' and os.path.exists(path(args, 'docs.parquet')):
            print('sample: docs.parquet exists, reused')
            continue
        print(f'\n=== {step}', flush=True)
        run[step](args)


if __name__ == '__main__':
    main()
