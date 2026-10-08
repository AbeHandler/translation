#!/usr/bin/env python
"""
Fightin' Words (src/fightin) between English and Chinese AI coverage: which phrases (or words) each emphasises more,
with Chinese units put on the English vocabulary by a multilingual embedding (each Chinese unit -> its nearest
English unit, src/fightin/concepts.py).

One run is one experiment: a selection (config/fightin_selections.tsv: all AI documents, those naming OpenAI,
Anthropic ...) at a sample size, with its own sample, embeddings and comparison, in results/fightin/<selection>_<n>k/
(openai_5k), so experiments never collide. scripts/go_fightin.sh submits every selection at 1k, 5k and 20k.
    sample   up to -n AI documents per language in the selection, random files and row groups, at most -per-file
             from each file (a second pass takes every match left if that falls short):
                 Chinese: the site crawls (data/interim/site_crawls/*/html), Chinese and about AI (primary_sources
                 chinese_ai_page); sampled first, as the smaller pool
                 English: CC-NEWS pages (data/interim/cc_html), tagged English, saying "AI" at least
                 twice, not templated stock notices, at most n/100 from one outlet, dated by crawl
             the selection's pattern on title and text, and its dates; main text by readability -> docs.parquet
    words    the units counted (src/fightin/units.py): with -ngrams 2-3 (default) phrases of 2-3 words with content
             words at both ends, with -ngrams 1 words; English by regex, Chinese by jieba with the AI terms
                                                                             -> units_<unit>.parquet
    embed    units in at least -min-df documents of their language (at most -max-vocab), by LaBSE
                                                                             -> index_<unit>.npz
    compare  Chinese units -> English concepts (cosine >= -threshold); concepts in -stopwords left out
                                                                             -> concepts_<unit>.tsv
             Fightin' Words over concepts used -min-count+ times, in either language or both (a Chinese-only
             phrase like 深度融合 counts 0 in English, glossed by its nearest English phrase: ≈ deep integration),
             English (i) vs Chinese (j): log-odds with an informative Dirichlet prior (-alpha0; background: both)
             plus -smooth on every count, z                                  -> fightin_<unit>.tsv
             the funnel plot (font: bash scripts/fetch_cjk_font.sh)          -> funnel_<unit>.png
    all      the steps in order: each language's sample is reused unless its sampling changed (SAMPLE_VERSION),
             embed if the index has exactly the units; the rest always rerun, so after any change one run redoes
             what's needed
    flush    deletes results/fightin/<experiment>/

Run as a module from the repo root (normally: bash scripts/go_fightin.sh):
    python -m scripts.fightin -selection openai -n 5000
    python -m scripts.fightin -selection all -n 20000 -ngrams 1        # words, on the same sample as phrases
"""
import argparse
import glob
import json
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
from src.fightin.concepts import (EMBED_VERSION, concept_counts, for_embedding, nearest_pivots, pivot_concepts,
                                  read_stopwords)
from src.fightin.counts import GroupCounts
from src.fightin.documents import is_templated
from src.fightin.embeddings.backends import from_encoder
from src.fightin.embeddings.index import VectorIndex
from src.fightin.measures import dirichlet_prior, log_odds_dirichlet
from src.fightin.plot import chinese_form, funnel_plot_tsv
from src.fightin.select import read_selections
from src.fightin.units import CJK, parse_ns, units
from src.primary_sources import chinese_ai_page
from src.source_texts import html_text

NAME = 'fightin'
STEPS = ('sample', 'words', 'embed', 'compare')
MIN_TEXT_CHARS = 300
# raise a language's number when its sampling changes: its sample is then drawn again (the other's is kept)
SAMPLE_VERSION = {'en': 3, 'zh': 1}   # en 3: no templated stock notices, outlet cap
GLOSS_MIN = 0.5      # a Chinese-only concept's nearest English unit is shown as its gloss from this cosine


def parse_args():
    parser = argparse.ArgumentParser(description="Fightin' Words between English and Chinese AI coverage")
    parser.add_argument('-step', default='all', choices=STEPS + ('all', 'flush'))
    parser.add_argument('-selection', default='all', help='which documents to sample: a name in -selections')
    parser.add_argument('-n', type=int, default=20000, help='documents per language (fewer if fewer match)')
    parser.add_argument('-experiment-name', default=None, help='default: <selection>_<n in thousands>k')
    parser.add_argument('-per-file', type=int, default=100, help='at most this many documents from one file')
    parser.add_argument('-ngrams', default='2-3', help="unit: '2-3' = phrases of 2 to 3 words; 1 = words")
    parser.add_argument('-selections', default=str(FIGHTIN_SELECTIONS_PATH), help='the selections table')
    parser.add_argument('-min-df', type=int, default=5, help='units in fewer documents of their language: no vector')
    parser.add_argument('-max-vocab', type=int, default=30000, help='embed at most this many units per language')
    parser.add_argument('-threshold', type=float, default=None,
                        help='Chinese unit -> English concept at this cosine (default 0.6 for words, 0.7 phrases)')
    parser.add_argument('-alpha0', type=float, default=1000, help="the prior's size (the paper's alpha_0)")
    parser.add_argument('-smooth', type=float, default=1.0, help='pseudo-count added to every count (on the prior)')
    parser.add_argument('-min-count', type=int, default=20, help='concepts used fewer times (both languages): left out')
    parser.add_argument('-stopwords', default=str(STOPWORDS_EN_PATH), help="concepts left out; '' keeps all")
    parser.add_argument('-min-docs', type=int, default=30, help='fewer documents in a language: an error')
    parser.add_argument('-seed', type=int, default=0)
    parser.add_argument('-cc-html-dir', default=str(CC_HTML_DIR))
    parser.add_argument('-crawls-dir', default=str(SITE_CRAWLS_DIR))
    args = parser.parse_args()
    selections = read_selections(args.selections)
    if args.selection not in selections:
        raise SystemExit(f'no selection {args.selection!r} in {args.selections}: one of {", ".join(selections)}')
    args.sel = selections[args.selection]
    size = f'{args.n // 1000}k' if args.n % 1000 == 0 else str(args.n)
    args.experiment_name = args.experiment_name or f'{args.selection}_{size}'
    args.out = os.path.join(REPO_ROOT, 'results', NAME, args.experiment_name)
    args.ns = parse_ns(args.ngrams)
    args.unit_name = 'words' if args.ns == (1,) else 'phrases'
    args.unit = 'words' if args.ns == (1,) else f'ngrams{args.ngrams}'
    args.threshold = args.threshold or (0.6 if args.ns == (1,) else 0.7)
    args.stop = read_stopwords(args.stopwords) if args.stopwords else frozenset()
    return args


def path(args, name):
    """A file of the experiment: docs.parquet is shared by words and phrases; the rest carry the unit
    (units_ngrams2-3.parquet, fightin_words.tsv)."""
    if name == 'docs.parquet':
        return os.path.join(args.out, name)
    stem, ext = os.path.splitext(name)
    return os.path.join(args.out, f'{stem}_{args.unit}{ext}')


def english_doc(row, sel):
    """{title, text, date} of an English CC-NEWS page about AI in the selection, else None; not a templated stock
    notice (src/fightin/documents.py). The language is CC-NEWS's tag, which is wrong for a few pages (Romanian ones
    gave "apare prima"): a language check could go here if that keeps showing up."""
    if not (row.get('language') or '').startswith('en') or not sel.may_match(row['html']) \
            or mentions_ai_html(row['html'])[0] < 2:
        return None
    title, text = html_text(row['html'].decode('utf-8', errors='replace'))
    date = (row.get('warc_date') or '')[:10]      # crawl date, near publication
    if len(text) < MIN_TEXT_CHARS or not mentions_ai(text) or not sel.matches(title, text, date) \
            or is_templated(text):
        return None
    return {'title': title, 'text': text, 'date': date}


def chinese_doc(row, sel):
    """{title, text, date} of a Chinese crawled page about AI in the selection, else None."""
    if not sel.may_match(row['html']):
        return None
    page = chinese_ai_page(row, '9999-12-31')
    if page is None:
        return None
    title, text = html_text(page[0])
    return {'title': title, 'text': text, 'date': page[1]} \
        if len(text) >= MIN_TEXT_CHARS and sel.matches(title, text, page[1]) else None


def sample_language(paths, read_doc, lang, args, rng, columns=('url', 'language', 'html'), per_outlet=None):
    """Up to args.n documents: files in random order, each file's row groups in random order, at most
    args.per_file documents from one file (so no outlet dominates). If that falls short (a narrow selection), a
    second pass takes every matching document left, so the sample is then all there is. Fewer than args.min_docs:
    an error. per_outlet: at most this many documents from one outlet (English: thousands of outlets, some of
    them content farms)."""
    docs, seen, outlets = [], set(), Counter()
    rng.shuffle(paths)
    for cap in (args.per_file, None):
        for n, file in enumerate(paths, 1):
            try:
                reader = pq.ParquetFile(file)
                groups = list(range(reader.num_row_groups))
                rng.shuffle(groups)
                found = 0
                for g in groups:
                    for row in reader.read_row_group(g, columns=list(columns)).to_pylist():
                        outlet = registered_domain(row['url'])
                        if row['url'] in seen or (per_outlet and outlets[outlet] >= per_outlet):
                            continue
                        try:
                            doc = read_doc(row)
                        except Exception:     # one unparseable page shouldn't stop the sample
                            continue
                        if doc:
                            seen.add(row['url'])
                            outlets[outlet] += 1
                            docs.append({'lang': lang, 'url': row['url'], 'outlet': outlet,
                                         'date': doc.get('date', ''), 'title': doc['title'], 'text': doc['text']})
                            found += 1
                        if (cap and found >= cap) or len(docs) >= args.n:
                            break
                    if (cap and found >= cap) or len(docs) >= args.n:
                        break
            except Exception as e:
                print(f'  skipped {file}: {e}', flush=True)
            if n % 50 == 0 or len(docs) >= args.n:
                print(f'  {lang}: {n}/{len(paths)} files read, {len(docs)}/{args.n} documents', flush=True)
            if len(docs) >= args.n:
                return docs
        if cap:
            print(f'  {lang}: {len(docs)} documents at {cap} per file; a second pass takes every match left',
                  flush=True)
    print(f'  {lang}: all {len(docs)} matching documents taken (fewer than {args.n})', flush=True)
    if len(docs) < args.min_docs:
        raise SystemExit(f'only {len(docs)} {lang} documents match selection {args.selection}; '
                         f'need {args.min_docs} (-min-docs)')
    return docs


def sample_step(args):
    """Each language's sample is reused if docs.parquet has it at the current SAMPLE_VERSION (docs.version), else
    drawn again; so a change to one language's sampling redoes only that language."""
    rng = random.Random(args.seed)
    old = pd.read_parquet(path(args, 'docs.parquet')) if os.path.exists(path(args, 'docs.parquet')) else None
    version_file = os.path.join(args.out, 'docs.version')
    versions = json.load(open(version_file)) if os.path.exists(version_file) else {'en': 1, 'zh': 1}
    english_per_outlet = max(10, args.n // 100)
    draws = {   # Chinese first: the crawls are the smaller pool, so a selection too narrow fails sooner
        'zh': lambda: sample_language(glob.glob(os.path.join(args.crawls_dir, '*', 'html', '*.parquet')),
                                      lambda row: chinese_doc(row, args.sel), 'zh', args, rng),
        'en': lambda: sample_language(glob.glob(os.path.join(args.cc_html_dir, '*.parquet')),
                                      lambda row: english_doc(row, args.sel), 'en', args, rng,
                                      columns=('url', 'language', 'warc_date', 'html'),
                                      per_outlet=english_per_outlet)}
    parts = []
    for lang, draw in draws.items():
        if old is not None and (old['lang'] == lang).any() and versions.get(lang) == SAMPLE_VERSION[lang]:
            print(f'{lang}: sample reused (version {SAMPLE_VERSION[lang]})')
            parts.append(old[old['lang'] == lang])
        else:
            print(f'{lang}: sampling (version {SAMPLE_VERSION[lang]})', flush=True)
            parts.append(pd.DataFrame(draw()))
    docs = pd.concat(parts, ignore_index=True)
    docs.to_parquet(path(args, 'docs.parquet'))
    with open(version_file, 'w') as f:
        json.dump(SAMPLE_VERSION, f)
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
    version_file = path(args, 'index.version')
    if os.path.exists(path(args, 'index.npz')) and os.path.exists(version_file) \
            and open(version_file).read().strip() == str(EMBED_VERSION):
        old = VectorIndex.load(path(args, 'index.npz'))
        if set(old.position) == {(lang, w) for lang, ws in wanted.items() for w in ws}:
            print(f"{path(args, 'index.npz')} already has these {args.unit_name}, reused")
            return
    labse_encode = labse()

    def encode(units_):      # abbreviations spelled out for the embedding only (src/fightin/concepts.py)
        return labse_encode([for_embedding(u) for u in units_])
    index = VectorIndex()
    for lang, ws in wanted.items():
        print(f'embedding {len(ws)} {lang} {args.unit_name}', flush=True)
        index.add(*from_encoder(ws, encode, say=lambda line: print(line, flush=True)), lang=lang)
    index.save(path(args, 'index.npz'))
    with open(version_file, 'w') as f:
        f.write(f'{EMBED_VERSION}\n')


def fight(args, docs, mapping, nearest, nearest_zh):
    """The English vs Chinese documents -> concepts, fightin and funnel files. Concepts used in one language only
    are kept (count 0 on the other side): Chinese phrases with no English counterpart (深度融合) are often the most
    telling. But a one-language concept with a close counterpart in the other language (cosine >= -threshold) is
    left out: its meaning is counted under that counterpart's concept, and it is one only because the languages cut
    phrases differently (English "chip export" inside "chip export controls"; jieba keeps 出口管制 whole). Every count
    is smoothed by -smooth on top of the prior, so a 0 stays finite."""
    zh_docs, en_docs = docs.loc[docs['lang'] == 'zh', 'units'], docs.loc[docs['lang'] == 'en', 'units']
    zh_counts, en_counts = concept_counts(zh_docs, mapping, args.stop), concept_counts(en_docs, None, args.stop)
    zh_unit_counts = Counter(w for d in zh_docs for w in d)
    members = defaultdict(Counter)       # concept -> its Chinese units, by count
    for w, n in zh_unit_counts.items():
        members[mapping[w][0]][w] = n
    concepts = pd.DataFrame([{'word': w, 'concept': c, 'similarity': round(s, 3), 'count': zh_unit_counts[w],
                              'nearest_english': nearest.get(w, ('', 0))[0]}
                             for w, (c, s) in mapping.items() if zh_unit_counts[w]])
    concepts.sort_values('count', ascending=False).to_csv(path(args, 'concepts.tsv'), sep='\t', index=False)

    def kept(c):        # used in both languages, or in one with nothing close in the other
        if en_counts[c] and zh_counts[c]:
            return True
        near = nearest_zh.get(c) if en_counts[c] else nearest.get(c)
        return near is None or near[1] < args.threshold
    vocab = sorted(c for c in set(en_counts) | set(zh_counts)
                   if en_counts[c] + zh_counts[c] >= args.min_count and kept(c))
    counts = GroupCounts(vocab, np.array([en_counts[c] for c in vocab], float),
                         np.array([zh_counts[c] for c in vocab], float))
    lo = log_odds_dirichlet(counts, alpha=dirichlet_prior(counts, alpha0=args.alpha0) + args.smooth)
    zh_forms = {c: ' '.join(w for w, _ in members[c].most_common(3)) for c in vocab}

    def english(c):     # a Chinese-only concept is glossed by its nearest English unit, if at all close
        if not CJK.search(c):
            return c
        return f'≈ {nearest[c][0]}' if c in nearest and nearest[c][1] >= GLOSS_MIN else ''
    kind = ['both' if en_counts[c] and zh_counts[c] else 'en only' if en_counts[c] else 'zh only' for c in vocab]
    english_forms = [english(c) for c in vocab]
    labels = [f'{e} / {chinese_form(zh_forms[c])}'.strip(' /') for c, e in zip(vocab, english_forms)]
    table = pd.DataFrame({'concept': vocab, 'english': english_forms, 'zh_forms': [zh_forms[c] for c in vocab],
                          'label': labels, 'kind': kind, 'en': counts.i, 'zh': counts.j, 'delta': lo.delta, 'z': lo.z})
    table = table.sort_values('z', ascending=False)
    table.to_csv(path(args, 'fightin.tsv'), sep='\t', index=False, float_format='%.4g')
    funnel_plot_tsv(path(args, 'fightin.tsv'), path(args, 'funnel.png'),
                    font_paths=sorted(FONTS_DIR.glob('*.[ot]tf')),
                    title=f"Fightin' Words: English vs Chinese AI ({args.experiment_name}, {args.unit_name})")
    print(f'  {len(vocab)} concepts with {args.min_count}+ uses: ' +
          ', '.join(f'{n} {k}' for k, n in pd.Series(kind).value_counts().items()))
    print('  most English:', ', '.join(table['label'].head(10)))
    print('  most Chinese:', ', '.join(table['label'].tail(10)[::-1]))
    print(f"  -> {path(args, 'fightin.tsv')}, {path(args, 'funnel.png')}")


def compare_step(args):
    docs = pd.read_parquet(path(args, 'docs.parquet'))
    index = VectorIndex.load(path(args, 'index.npz'))
    print(f"{args.unit_name} of {(docs['lang'] == 'en').sum()} English and {(docs['lang'] == 'zh').sum()} Chinese "
          'documents', flush=True)
    docs['units'] = [doc_units(t, lang, args) for t, lang in zip(docs['text'], docs['lang'])]
    zh_units = sorted({w for d in docs.loc[docs['lang'] == 'zh', 'units'] for w in d})
    nearest = nearest_pivots(index, zh_units)
    mapping = pivot_concepts(index, zh_units, args.threshold, nearest=nearest)
    mapped = sum(1 for c, s in mapping.values() if s >= args.threshold)
    print(f'{len(mapping)} Chinese {args.unit_name}, {mapped} mapped to an English one (cosine >= {args.threshold})')
    en_units = sorted({w for d in docs.loc[docs['lang'] == 'en', 'units'] for w in d})
    fight(args, docs, mapping, nearest, nearest_pivots(index, en_units, source='en', pivot='zh'))
    print(f'\nSpot checks:\n  head -30 {path(args, "fightin.tsv")} | column -t -s $\'\\t\'')
    print(f"  sort -t$'\\t' -k3 -g {path(args, 'concepts.tsv')} | tail -40      # the closest calls at the threshold")


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
        print(f'\n=== {step}', flush=True)
        run[step](args)


if __name__ == '__main__':
    main()
