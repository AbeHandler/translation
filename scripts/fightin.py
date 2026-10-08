#!/usr/bin/env python
"""
Fightin' Words (src/fightin) between English and Chinese AI coverage: which concepts each emphasises more, with
English and Chinese words (or phrases) put on one vocabulary by a multilingual embedding (each Chinese unit -> its
nearest English unit, src/fightin/concepts.py). All outputs in results/fightin/<experiment_name>/; phrase runs'
files carry a suffix (fightin_ngrams2-3.tsv ...), so words and phrases share one sample:
    sample   -n AI documents per language, random files and row groups, at most -per-file from each file:
                 English: CC-NEWS pages (data/interim/cc_html), English, saying "AI" at least twice
                 Chinese: the site crawls (data/interim/site_crawls/*/html), Chinese and about AI (primary_sources
                 chinese_ai_page)
             main text by readability                                        -> docs.parquet
    words    the units counted (src/fightin/units.py): words, or with -ngrams 2-3 phrases of 2-3 words with content
             words at both ends; English by regex, Chinese by jieba with the AI terms
                                                                             -> words.parquet (lang, word, count, df)
    embed    units in at least -min-df documents of their language (at most -max-vocab), by LaBSE
                                                                             -> index.npz (src/fightin/embeddings)
             (each word encoded as a one-word sentence; contextual word vectors averaged over the corpus would be
             truly word-level: see src/fightin/embeddings/backends.py)
    select   conditioning: which documents to compare. -selection all (default): the whole sample; otherwise a
             named list of document ids, from -ids (any file of ids, one per line) or made here by -pattern (regex on
             title and text, e.g. 'OpenAI' or 'Anthropic|Claude') and -from/-to (dates; English: CC-NEWS crawl date)
                                                                             -> selections/<name>.txt
    fight    Chinese words -> English concepts (cosine >= -threshold)        -> concepts.tsv
             English documents count only Latin-script words; concepts in -stopwords are left out (function words
             have no counterpart across languages: 该 -> the, 以及 -> and)
             Fightin' Words over concepts used in both languages, English (i) vs Chinese (j) of the selection:
             log-odds with an informative Dirichlet prior (-alpha0; the background is the whole sample), z-scores
                                                                             -> fightin.tsv
    plot     the funnel plot: z against frequency, top 20 concepts each side    -> funnel.png
             (Chinese labels need a Chinese font: bash scripts/fetch_cjk_font.sh puts one in data/external/fonts;
             or redraw on a laptop from fightin.tsv: scripts/plot_fightin.py)
    all      the steps in order: sample skips if docs.parquet exists, embed if index.npz has exactly the units
             to embed; the rest (minutes) always rerun, so after any change one run of -step all redoes what's needed
    flush    deletes results/fightin/<experiment_name>/

Run as a module from the repo root (normally via scripts/slurm/fightin.slurm):
    python -m scripts.fightin -step all
    python -m scripts.fightin -step all -ngrams 2-3     # phrases: same docs.parquet, outputs *_ngrams2-3.*
    python -m scripts.fightin -step all -selection openai -pattern 'OpenAI'     # outputs *_openai.*
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

from config.paths import CC_HTML_DIR, FONTS_DIR, REPO_ROOT, SITE_CRAWLS_DIR, STOPWORDS_EN_PATH
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
STEPS = ('sample', 'words', 'embed', 'select', 'fight', 'plot')
REUSED = ('sample',)    # -step all skips it if docs.parquet exists; embed reuses index.npz if its vocabulary matches
MIN_TEXT_CHARS = 300


def parse_args():
    parser = argparse.ArgumentParser(description="Fightin' Words between English and Chinese AI coverage")
    parser.add_argument('-step', required=True, choices=STEPS + ('all', 'flush'))
    parser.add_argument('-experiment-name', default='en_vs_zh_ai')
    parser.add_argument('-n', type=int, default=2000, help='documents per language')
    parser.add_argument('-per-file', type=int, default=20, help='at most this many documents from one file')
    parser.add_argument('-min-df', type=int, default=5, help='words in fewer documents of their language: no vector')
    parser.add_argument('-ngrams', default='1', help="unit: 1 = words; '2-3' = phrases of 2 to 3 words")
    parser.add_argument('-max-vocab', type=int, default=30000, help='embed at most this many units per language')
    parser.add_argument('-threshold', type=float, default=None,
                        help='Chinese unit -> English concept at this cosine (default 0.6 for words, 0.7 phrases)')
    parser.add_argument('-alpha0', type=float, default=1000, help="the prior's size (the paper's alpha_0)")
    parser.add_argument('-stopwords', default=str(STOPWORDS_EN_PATH), help="concepts left out; '' keeps all")
    parser.add_argument('-selection', default='all',
                        help="the documents compared: 'all' (the whole sample), or a name for a selection made by "
                             "-pattern/-from/-to, or read from -ids")
    parser.add_argument('-pattern', default=None, help="selection: regex on title and text, e.g. 'OpenAI'")
    parser.add_argument('-from', dest='start', default=None, help='selection: documents dated on or after (YYYY-MM-DD)')
    parser.add_argument('-to', dest='end', default=None, help='selection: documents dated on or before')
    parser.add_argument('-ids', default=None, help='selection: a file of document ids (scripts/fightin docs.parquet '
                                                   'url -> src/fightin/select.py doc_id), one per line')
    parser.add_argument('-min-docs', type=int, default=30, help='a selection needs this many documents per language')
    parser.add_argument('-seed', type=int, default=0)
    parser.add_argument('-cc-html-dir', default=str(CC_HTML_DIR))
    parser.add_argument('-crawls-dir', default=str(SITE_CRAWLS_DIR))
    args = parser.parse_args()
    args.out = os.path.join(REPO_ROOT, 'results', NAME, args.experiment_name)
    args.ns = parse_ns(args.ngrams)
    args.unit_name = 'words' if args.ns == (1,) else 'phrases'
    args.suffix = '' if args.ns == (1,) else f'_ngrams{args.ngrams}'   # words and phrases share docs.parquet
    args.threshold = args.threshold or (0.6 if args.ns == (1,) else 0.7)
    args.stop = read_stopwords(args.stopwords) if args.stopwords else frozenset()
    if args.selection == 'all' and (args.pattern or args.start or args.end or args.ids):
        raise SystemExit('-pattern, -from, -to and -ids need a -selection name')
    return args


PER_SELECTION = ('concepts.tsv', 'fightin.tsv', 'funnel.png')


def path(args, name):
    """A file of the experiment. Per-unit outputs (all but docs.parquet) carry the unit's suffix (_ngrams2-3), the
    comparison's outputs also the selection's (_openai); selections live in selections/<name>.txt."""
    if name != 'docs.parquet':
        stem, ext = os.path.splitext(name)
        selection = f'_{args.selection}' if name in PER_SELECTION and args.selection != 'all' else ''
        name = f'{stem}{args.suffix}{selection}{ext}'
    return os.path.join(args.out, name)


def selection_path(args):
    return os.path.join(args.out, 'selections', f'{args.selection}.txt')


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
        raise SystemExit(f'only {len(docs)} {lang} documents found in {len(paths)} files; lower -n')
    return docs


def sample_step(args):
    rng = random.Random(args.seed)
    en = sample_language(glob.glob(os.path.join(args.cc_html_dir, '*.parquet')), english_doc, 'en', args, rng,
                         columns=('url', 'language', 'warc_date', 'html'))
    zh = sample_language(glob.glob(os.path.join(args.crawls_dir, '*', 'html', '*.parquet')), chinese_doc, 'zh',
                         args, rng)
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
    words.to_parquet(path(args, 'words.parquet'))
    for lang, group in words.groupby('lang'):
        print(f'{lang}: {len(group)} {args.unit_name}, {group["count"].sum()} occurrences, '
              f'{(group["df"] >= args.min_df).sum()} in {args.min_df}+ documents')


def embed_step(args):
    from src.dispersion.encoders import labse
    words = pd.read_parquet(path(args, 'words.parquet'))
    wanted = {lang: group.sort_values('df', ascending=False).head(args.max_vocab)['word'].tolist()
              for lang, group in words[words['df'] >= args.min_df].groupby('lang')}
    if os.path.exists(path(args, 'index.npz')):
        old = VectorIndex.load(path(args, 'index.npz'))
        if set(old.position) == {(lang, w) for lang, ws in wanted.items() for w in ws}:
            print('index.npz already has these units, reused')
            return
    encode = labse()
    index = VectorIndex()
    for lang, ws in wanted.items():
        print(f'embedding {len(ws)} {lang} {args.unit_name}', flush=True)
        index.add(*from_encoder(ws, encode, say=lambda line: print(line, flush=True)), lang=lang)
    index.save(path(args, 'index.npz'))


def select_step(args):
    """The selection's document ids -> selections/<name>.txt (from -ids, or -pattern/-from/-to on the sample)."""
    if args.selection == 'all':
        print('selection: all documents of the sample')
        return
    docs = pd.read_parquet(path(args, 'docs.parquet'))
    ids = sorted(read_ids(args.ids)) if args.ids else select_ids(docs, args.pattern, args.start, args.end)
    os.makedirs(os.path.dirname(selection_path(args)), exist_ok=True)
    write_ids(ids, selection_path(args))
    chosen = docs[docs['url'].map(doc_id).isin(set(ids))]
    per_lang = chosen['lang'].value_counts().reindex(['en', 'zh'], fill_value=0)
    print(f"selection {args.selection}: {per_lang['en']} English, {per_lang['zh']} Chinese documents "
          f"(of {len(docs)}) -> {selection_path(args)}")
    if per_lang.min() < args.min_docs:
        raise SystemExit(f'selection {args.selection}: fewer than {args.min_docs} documents in a language; '
                         'loosen it, or sample more (N)')


def fight_step(args):
    docs = pd.read_parquet(path(args, 'docs.parquet'))
    index = VectorIndex.load(path(args, 'index.npz'))
    docs['units'] = [doc_units(t, lang, args) for t, lang in zip(docs['text'], docs['lang'])]
    mapping = pivot_concepts(index, sorted({w for d in docs.loc[docs['lang'] == 'zh', 'units'] for w in d}),
                             args.threshold)
    pool = concept_counts(docs.loc[docs['lang'] == 'zh', 'units'], mapping, args.stop) + \
        concept_counts(docs.loc[docs['lang'] == 'en', 'units'], None, args.stop)    # the prior's background
    if args.selection != 'all':
        docs = docs[docs['url'].map(doc_id).isin(read_ids(selection_path(args)))]
    zh_docs, en_docs = docs.loc[docs['lang'] == 'zh', 'units'], docs.loc[docs['lang'] == 'en', 'units']
    print(f'{len(en_docs)} English and {len(zh_docs)} Chinese documents ({args.selection})')
    zh_counts, en_counts = concept_counts(zh_docs, mapping, args.stop), concept_counts(en_docs, None, args.stop)
    zh_word_counts = Counter(w for d in zh_docs for w in d)
    members = defaultdict(Counter)       # concept -> its Chinese words, by count
    for w, n in zh_word_counts.items():
        members[mapping[w][0]][w] = n
    concepts = pd.DataFrame([{'word': w, 'concept': c, 'similarity': round(s, 3), 'count': zh_word_counts[w]}
                             for w, (c, s) in mapping.items() if zh_word_counts[w]])
    concepts.sort_values('count', ascending=False).to_csv(path(args, 'concepts.tsv'), sep='\t', index=False)

    shared = sorted(c for c in en_counts if zh_counts.get(c))
    counts = GroupCounts(shared, np.array([en_counts[c] for c in shared], float),
                         np.array([zh_counts[c] for c in shared], float), np.array([pool[c] for c in shared], float))
    lo = log_odds_dirichlet(counts, alpha0=args.alpha0)
    zh_forms = {c: ' '.join(w for w, _ in members[c].most_common(3)) for c in shared}
    labels = [f'{c} / {chinese_form(zh_forms[c])}' if chinese_form(zh_forms[c]) else c for c in shared]
    table = pd.DataFrame({'concept': shared, 'zh_forms': [zh_forms[c] for c in shared], 'label': labels,
                          'en': counts.i, 'zh': counts.j, 'delta': lo.delta, 'z': lo.z})
    table = table.sort_values('z', ascending=False)
    table.to_csv(path(args, 'fightin.tsv'), sep='\t', index=False, float_format='%.4g')
    mapped = sum(1 for c, s in mapping.values() if s >= args.threshold)
    print(f'{len(mapping)} Chinese {args.unit_name}: {mapped} mapped to an '
          f'English concept; {len(shared)} concepts used in both languages')
    print('\nmost English:', ', '.join(table['concept'].head(20)))
    tail = table.tail(20)[::-1]
    print('most Chinese:', ', '.join(f'{c} ({f})' for c, f in zip(tail['concept'], tail['zh_forms'])))
    print(f"\n-> {path(args, 'fightin.tsv')}, {path(args, 'concepts.tsv')}")
    print('Spot checks:')
    print(f"  head -30 {path(args, 'fightin.tsv')} | column -t -s $'\\t'")
    print(f"  awk -F'\\t' '$2==\"governance\"' {path(args, 'concepts.tsv')}       # the Chinese words behind a concept")
    print(f"  sort -t$'\\t' -k3 -g {path(args, 'concepts.tsv')} | tail -40      # the closest calls at the threshold")


def plot_step(args):
    funnel_plot_tsv(path(args, 'fightin.tsv'), path(args, 'funnel.png'), font_paths=sorted(FONTS_DIR.glob('*.[ot]tf')),
                    title=f"Fightin' Words: English vs Chinese AI ({args.experiment_name}, {args.unit_name}, "
                          f"{args.selection})")
    print(f"-> {path(args, 'funnel.png')}")


def flush_step(args):
    if os.path.isdir(args.out):
        shutil.rmtree(args.out)
        print(f'deleted {args.out}')


def main():
    args = parse_args()
    if args.step == 'flush':
        return flush_step(args)
    os.makedirs(args.out, exist_ok=True)
    outputs = {'sample': 'docs.parquet'}
    run = {'sample': sample_step, 'words': words_step, 'embed': embed_step, 'select': select_step, 'fight': fight_step,
           'plot': plot_step}
    for step in STEPS if args.step == 'all' else (args.step,):
        if args.step == 'all' and step in REUSED and os.path.exists(path(args, outputs[step])):
            print(f'{step}: {outputs[step]} exists, skipped')
            continue
        print(f'--- {step}', flush=True)
        run[step](args)


if __name__ == '__main__':
    main()
