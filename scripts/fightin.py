#!/usr/bin/env python
"""
Fightin' Words (src/fightin) between English and Chinese AI coverage: which concepts each emphasises more, with
English and Chinese words put on one vocabulary by a multilingual embedding (each Chinese word -> its nearest
English word, src/fightin/concepts.py). All outputs in results/fightin/<experiment_name>/:
    sample   -n AI documents per language, random files and row groups, at most -per-file from each file:
                 English: CC-NEWS pages (data/interim/cc_html), English, saying "AI" at least twice
                 Chinese: the site crawls (data/interim/site_crawls/*/html), Chinese and about AI (primary_sources
                 chinese_ai_page)
             main text by readability                                        -> docs.parquet
    words    tokens (English regex, Chinese jieba with the AI terms), counted -> words.parquet (lang, word, count, df)
    embed    words in at least -min-df documents of their language, by LaBSE -> index.npz (src/fightin/embeddings)
             (each word encoded as a one-word sentence; contextual word vectors averaged over the corpus would be
             truly word-level: see src/fightin/embeddings/backends.py)
    fight    Chinese words -> English concepts (cosine >= -threshold)        -> concepts.tsv
             Fightin' Words over concepts used in both languages, English (i) vs Chinese (j): log-odds with an
             informative Dirichlet prior (-alpha0; the background is both groups), z-scores
                                                                             -> fightin.tsv
    plot     the funnel plot: z against frequency, top 20 concepts each side    -> funnel.png
             (Chinese labels need a Chinese font: bash scripts/fetch_cjk_font.sh puts one in data/external/fonts;
             or redraw on a laptop from fightin.tsv: scripts/plot_fightin.py)
    all      the steps in order (each skips if its output exists)
    flush    deletes results/fightin/<experiment_name>/

Run as a module from the repo root (normally via scripts/slurm/fightin.slurm):
    python -m scripts.fightin -step all
    python -m scripts.fightin -step fight -threshold 0.7 -experiment-name t07   # needs the earlier steps' outputs
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

from config.paths import CC_HTML_DIR, FONTS_DIR, REPO_ROOT, SITE_CRAWLS_DIR
from src.ai_mentions import mentions_ai, mentions_ai_html
from src.dispersion.tokens import tokens
from src.external_links import registered_domain
from src.fightin.concepts import concept_counts, normalise, pivot_concepts
from src.fightin.counts import GroupCounts
from src.fightin.embeddings.backends import from_encoder
from src.fightin.embeddings.index import VectorIndex
from src.fightin.measures import log_odds_dirichlet
from src.fightin.plot import funnel_plot_tsv
from src.primary_sources import chinese_ai_page
from src.source_texts import html_text

NAME = 'fightin'
STEPS = ('sample', 'words', 'embed', 'fight', 'plot')
MIN_TEXT_CHARS = 300


def parse_args():
    parser = argparse.ArgumentParser(description="Fightin' Words between English and Chinese AI coverage")
    parser.add_argument('-step', required=True, choices=STEPS + ('all', 'flush'))
    parser.add_argument('-experiment-name', default='en_vs_zh_ai')
    parser.add_argument('-n', type=int, default=2000, help='documents per language')
    parser.add_argument('-per-file', type=int, default=20, help='at most this many documents from one file')
    parser.add_argument('-min-df', type=int, default=5, help='words in fewer documents of their language: no vector')
    parser.add_argument('-threshold', type=float, default=0.6, help='Chinese word -> English concept at this cosine')
    parser.add_argument('-alpha0', type=float, default=1000, help="the prior's size (the paper's alpha_0)")
    parser.add_argument('-seed', type=int, default=0)
    parser.add_argument('-cc-html-dir', default=str(CC_HTML_DIR))
    parser.add_argument('-crawls-dir', default=str(SITE_CRAWLS_DIR))
    args = parser.parse_args()
    args.out = os.path.join(REPO_ROOT, 'results', NAME, args.experiment_name)
    return args


def path(args, name):
    return os.path.join(args.out, name)


def english_doc(row):
    """{title, text} of an English CC-NEWS page about AI, else None."""
    if not (row.get('language') or '').startswith('en') or mentions_ai_html(row['html'])[0] < 2:
        return None
    title, text = html_text(row['html'].decode('utf-8', errors='replace'))
    return {'title': title, 'text': text} if len(text) >= MIN_TEXT_CHARS and mentions_ai(text) else None


def chinese_doc(row):
    """{title, text, date} of a Chinese crawled page about AI, else None."""
    page = chinese_ai_page(row, '9999-12-31')
    if page is None:
        return None
    title, text = html_text(page[0])
    return {'title': title, 'text': text, 'date': page[1]} if len(text) >= MIN_TEXT_CHARS else None


def sample_language(paths, read_doc, lang, args, rng):
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
                for row in reader.read_row_group(g, columns=['url', 'language', 'html']).to_pylist():
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
    en = sample_language(glob.glob(os.path.join(args.cc_html_dir, '*.parquet')), english_doc, 'en', args, rng)
    zh = sample_language(glob.glob(os.path.join(args.crawls_dir, '*', 'html', '*.parquet')), chinese_doc, 'zh',
                         args, rng)
    docs = pd.DataFrame(en + zh)
    docs.to_parquet(path(args, 'docs.parquet'))
    print(docs.groupby('lang').agg(docs=('url', 'size'), outlets=('outlet', 'nunique'),
                                   median_chars=('text', lambda t: int(t.str.len().median()))))


def doc_words(text, lang):
    return [w for w in (normalise(t) for t, _, _ in tokens(text, lang)) if w]


def words_step(args):
    docs = pd.read_parquet(path(args, 'docs.parquet'))
    rows = []
    for lang, group in docs.groupby('lang'):
        count, df = Counter(), Counter()
        for text in group['text']:
            words = doc_words(text, lang)
            count.update(words)
            df.update(set(words))
        rows += [{'lang': lang, 'word': w, 'count': c, 'df': df[w]} for w, c in count.items()]
    words = pd.DataFrame(rows)
    words.to_parquet(path(args, 'words.parquet'))
    for lang, group in words.groupby('lang'):
        print(f'{lang}: {len(group)} words, {group["count"].sum()} tokens, {(group["df"] >= args.min_df).sum()} in '
              f'{args.min_df}+ documents')


def embed_step(args):
    from src.dispersion.encoders import labse
    encode = labse()
    words = pd.read_parquet(path(args, 'words.parquet'))
    index = VectorIndex()
    for lang, group in words[words['df'] >= args.min_df].groupby('lang'):
        print(f'embedding {len(group)} {lang} words', flush=True)
        index.add(*from_encoder(group.sort_values('count', ascending=False)['word'].tolist(), encode), lang=lang)
    index.save(path(args, 'index.npz'))


def fight_step(args):
    docs = pd.read_parquet(path(args, 'docs.parquet'))
    index = VectorIndex.load(path(args, 'index.npz'))
    zh_docs = [doc_words(t, 'zh') for t in docs.loc[docs['lang'] == 'zh', 'text']]
    en_docs = [doc_words(t, 'en') for t in docs.loc[docs['lang'] == 'en', 'text']]
    mapping = pivot_concepts(index, sorted({w for d in zh_docs for w in d}), args.threshold)
    zh_counts, en_counts = concept_counts(zh_docs, mapping), concept_counts(en_docs)
    zh_word_counts = Counter(w for d in zh_docs for w in d)
    members = defaultdict(Counter)       # concept -> its Chinese words, by count
    for w, n in zh_word_counts.items():
        members[mapping[w][0]][w] = n
    concepts = pd.DataFrame([{'word': w, 'concept': c, 'similarity': round(s, 3), 'count': zh_word_counts[w]}
                             for w, (c, s) in mapping.items()])
    concepts.sort_values('count', ascending=False).to_csv(path(args, 'concepts.tsv'), sep='\t', index=False)

    shared = sorted(c for c in en_counts if zh_counts.get(c))
    counts = GroupCounts(shared, np.array([en_counts[c] for c in shared], float),
                         np.array([zh_counts[c] for c in shared], float))
    lo = log_odds_dirichlet(counts, alpha0=args.alpha0)
    zh_forms = {c: ' '.join(w for w, _ in members[c].most_common(3)) for c in shared}
    labels = [c if zh_forms[c] == c else f'{c} / {zh_forms[c].split()[0]}' for c in shared]
    table = pd.DataFrame({'concept': shared, 'zh_forms': [zh_forms[c] for c in shared], 'label': labels,
                          'en': counts.i, 'zh': counts.j, 'delta': lo.delta, 'z': lo.z})
    table = table.sort_values('z', ascending=False)
    table.to_csv(path(args, 'fightin.tsv'), sep='\t', index=False, float_format='%.4g')
    print(f'{len(mapping)} Chinese words: {sum(1 for c, s in mapping.values() if s >= args.threshold)} mapped to an '
          f'English concept; {len(shared)} concepts used in both languages')
    print('\nmost English:', ', '.join(table['concept'].head(20)))
    tail = table.tail(20)[::-1]
    print('most Chinese:', ', '.join(f'{c} ({f})' for c, f in zip(tail['concept'], tail['zh_forms'])))
    print(f'\n-> {args.out}/{{fightin.tsv, concepts.tsv}}')
    print('Spot checks:')
    print(f"  head -30 {path(args, 'fightin.tsv')} | column -t -s $'\\t'")
    print(f"  awk -F'\\t' '$2==\"governance\"' {path(args, 'concepts.tsv')}       # the Chinese words behind a concept")
    print(f"  sort -t$'\\t' -k3 -g {path(args, 'concepts.tsv')} | tail -40      # the closest calls at the threshold")


def plot_step(args):
    funnel_plot_tsv(path(args, 'fightin.tsv'), path(args, 'funnel.png'), font_paths=sorted(FONTS_DIR.glob('*.[ot]tf')),
                    title=f"Fightin' Words: English vs Chinese AI ({args.experiment_name})")
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
    outputs = {'sample': 'docs.parquet', 'words': 'words.parquet', 'embed': 'index.npz', 'fight': 'fightin.tsv',
               'plot': 'funnel.png'}
    run = {'sample': sample_step, 'words': words_step, 'embed': embed_step, 'fight': fight_step, 'plot': plot_step}
    for step in STEPS if args.step == 'all' else (args.step,):
        if args.step == 'all' and os.path.exists(path(args, outputs[step])):
            print(f'{step}: {outputs[step]} exists, skipped')
            continue
        print(f'--- {step}', flush=True)
        run[step](args)


if __name__ == '__main__':
    main()
