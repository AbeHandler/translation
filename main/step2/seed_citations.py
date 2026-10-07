#!/usr/bin/env python
"""
Step 2: source transmission, the seeds' salience in English and Chinese news (model.md; src/salience.py).
    -step citations   a worker over the link tables of step 1 (data/interim/primary_sources{,_zh}/links/): each
                      file's articles that link a seed, with their text (English: data/interim/cc_html/<warc>.parquet;
                      Chinese: data/interim/site_crawls/<domain>/html/<part>.parquet) and the passages they quote
                      verbatim from the seed's text (data/processed/primary.pq)
                      -> data/interim/step2/{citations,quotes}/<en|zh>__<file>.parquet
    -step salience    all of them -> data/processed/seed_citations.parquet (seed, language, citing article, outlet,
                      date, title, text, n_passages), data/processed/seed_quotes.parquet (a link table: one row per
                      passage quoted verbatim from a seed by a citing article), data/processed/seed_salience.tsv
                      (one row per seed: per language, citing articles and outlets, outlets within 14 days, first
                      citation and lag, articles quoting it)
citations skips files already done; rerun after step 1. All of step 2: bash main/step2/go_step2.sh.

Run as a module from the repo root:
    python -m main.step2.seed_citations -step citations -max-files 1     # test
    python -m main.step2.seed_citations -step salience
"""
import argparse
import csv
import glob
import os
import random
from collections import Counter

import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq

from config.paths import (CC_HTML_DIR, PRIMARY_DB_PATH, PRIMARY_SOURCES_DIR, SEED_CITATIONS_PATH, SEED_QUOTES_PATH,
                          SEED_SALIENCE_PATH, SEEDS_PATH, SITE_CRAWLS_DIR, STEP2_DIR)
from src.cc_news import html_rows
from src.file_worker import process_files
from src.salience import CITATION_COLUMNS, QUOTE_COLUMNS, SALIENCE_COLUMNS, quoted_passages, seed_salience
from src.source_matching import phrases
from src.source_texts import html_text
from src.warc_worker_cli import optional_int, setup_worker_process


def schema(columns):
    return pa.schema([(name, getattr(pa, kind)()) for name, kind in columns])


def parse_args():
    parser = argparse.ArgumentParser(description="Step 2: the seeds' citing articles and salience")
    parser.add_argument('-step', required=True, choices=('citations', 'salience'))
    parser.add_argument('-seeds', default=str(SEEDS_PATH))
    parser.add_argument('-sources', default=str(PRIMARY_DB_PATH), help="the seeds' texts")
    parser.add_argument('-en-links', default=os.path.join(str(PRIMARY_SOURCES_DIR), 'links'))
    parser.add_argument('-zh-links', default=os.path.join(str(PRIMARY_SOURCES_DIR) + '_zh', 'links'))
    parser.add_argument('-cc-html-dir', default=str(CC_HTML_DIR))
    parser.add_argument('-crawls-dir', default=str(SITE_CRAWLS_DIR))
    parser.add_argument('-work-dir', default=str(STEP2_DIR))
    parser.add_argument('-out-citations', default=str(SEED_CITATIONS_PATH))
    parser.add_argument('-out-quotes', default=str(SEED_QUOTES_PATH))
    parser.add_argument('-out-salience', default=str(SEED_SALIENCE_PATH))
    parser.add_argument('-max-files', type=optional_int, default=None, help='citations: stop after N (testing)')
    return parser.parse_args()


def read_seeds(path):
    with open(path, encoding='utf-8', newline='') as f:
        return {r['key']: r for r in csv.DictReader(f, delimiter='\t')}


def html_path_of(lang, link_file, args):
    """The HTML file a link table was made from: a WARC's cc_html file, or a crawl's html part."""
    name = os.path.basename(link_file).removesuffix('.parquet')
    if lang == 'en':
        return os.path.join(args.cc_html_dir, name + '.parquet')
    domain, part = name.split('__', 1)
    return os.path.join(args.crawls_dir, domain, 'html', part + '.parquet')


def citations_step(args):
    seeds = read_seeds(args.seeds)
    texts = pd.read_parquet(args.sources, columns=['key', 'status', 'text'])
    texts = dict(zip(texts.key, texts.text.where(texts.status == 200, '')))
    seed_phrases = {}   # filled as seeds come up: phrase sets are large

    def phrases_of(key):
        if key not in seed_phrases:
            seed_phrases[key] = phrases(texts.get(key) or '')
        return seed_phrases[key]

    inputs = [('en', p) for p in glob.glob(os.path.join(args.en_links, '*.parquet'))]
    inputs += [('zh', p) for p in glob.glob(os.path.join(args.zh_links, '*.parquet'))]
    random.shuffle(inputs)
    lang_of = {p: lang for lang, p in inputs}
    for sub in ('citations', 'quotes'):
        os.makedirs(os.path.join(args.work_dir, sub), exist_ok=True)

    def out_path(path):
        return os.path.join(args.work_dir, 'citations', f'{lang_of[path]}__{os.path.basename(path)}')

    def extract(path, out):
        lang = lang_of[path]
        links = pq.read_table(path, columns=['document', 'article', 'outlet', 'date']).to_pylist()
        links = [r for r in links if r['document'] in seeds]
        html_path = html_path_of(lang, path, args)
        html = {}
        if links and os.path.exists(html_path):
            html = {r['url']: r['html'] for r in html_rows(html_path, {r['article'] for r in links})}
        text_of, cites, quotes = {}, [], []
        for r in links:
            if r['article'] not in text_of:
                raw = html.get(r['article'])
                raw = raw.decode('utf-8', errors='replace') if isinstance(raw, bytes) else (raw or '')
                text_of[r['article']] = html_text(raw) if raw else ('', '')
            title, text = text_of[r['article']]
            seed = seeds[r['document']]
            passages = quoted_passages(text, phrases_of(r['document'])) if text else []
            base = {'seed_id': seed['seed_id'], 'key': r['document'], 'language': lang, 'article': r['article'],
                    'outlet': r['outlet'], 'date': r['date']}
            cites.append({**base, 'title': title, 'text': text, 'n_chars': len(text), 'n_passages': len(passages),
                          'n_quoted_words': sum(len(p.split()) for p in passages)})
            quotes += [{**base, 'passage': p, 'n_words': len(p.split())} for p in passages]
        quotes_out = os.path.join(args.work_dir, 'quotes', os.path.basename(out))
        pq.write_table(pa.Table.from_pylist(quotes, schema(QUOTE_COLUMNS)), quotes_out + '.part')
        os.replace(quotes_out + '.part', quotes_out)
        pq.write_table(pa.Table.from_pylist(cites, schema(CITATION_COLUMNS)), out + '.part')
        os.replace(out + '.part', out)    # last: an existing citations file means this input is done
        return {'citations': len(cites), 'quotes': len(quotes)}
    process_files([p for _, p in inputs], out_path, extract, args.max_files)


def salience_step(args):
    seeds = read_seeds(args.seeds)
    cites = pq.ParquetDataset(os.path.join(args.work_dir, 'citations')).read()
    quotes = pq.ParquetDataset(os.path.join(args.work_dir, 'quotes')).read()
    pq.write_table(cites, args.out_citations, compression='zstd')
    pq.write_table(quotes, args.out_quotes, compression='zstd')
    by_seed = {}
    for c in cites.drop(['text', 'title']).to_pylist():
        by_seed.setdefault(c['key'], []).append(c)
    rows = [seed_salience(seed, by_seed.get(key, [])) for key, seed in seeds.items()]
    rows.sort(key=lambda r: -(r['en_outlets'] + r['zh_outlets']))
    with open(args.out_salience + '.part', 'w', encoding='utf-8', newline='') as f:
        writer = csv.DictWriter(f, SALIENCE_COLUMNS, delimiter='\t')
        writer.writeheader()
        writer.writerows(rows)
    os.replace(args.out_salience + '.part', args.out_salience)
    print(f'{cites.num_rows} citations of {len(by_seed)} of {len(seeds)} seeds -> {args.out_citations}')
    print(f'{quotes.num_rows} quoted passages -> {args.out_quotes}')
    print(f'{len(rows)} seeds -> {args.out_salience}')
    for lang in ('en', 'zh'):
        cited = [r for r in rows if r[f'{lang}_articles']]
        lags = sorted(r[f'{lang}_lag_days'] for r in cited if r[f'{lang}_lag_days'] != '')
        print(f'  {lang}: {len(cited)} seeds cited; median lag {lags[len(lags) // 2] if lags else "-"} days; '
              f'{sum(1 for r in cited if r[f"{lang}_quoting"])} quoted verbatim by at least one article')
    print('most-quoted passages:')
    q = quotes.select(['key', 'passage', 'outlet']).to_pandas()
    for (key, passage), n in Counter(zip(q.key, q.passage)).most_common(10):
        print(f'  {n:4d}  {passage[:80]!r}  <- {key[:60]}')


def main():
    setup_worker_process()
    args = parse_args()
    {'citations': citations_step, 'salience': salience_step}[args.step](args)


if __name__ == '__main__':
    main()
