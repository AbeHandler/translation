#!/usr/bin/env python
"""
Link the English screenshots in the Chinese crawls to the primary sources they show (src/source_matching.py):
each screenshot's OCR text against every fetched source in the store, kept if they share -min-shared five-word
phrases. One row per matched screenshot, strongest first:
    shared, source_url, source_title, kind, site, page, date, notable, accounts, src, ocr
shared is the number of five-word phrases in common; overlap is the passages they make up (lowercased, joined by
" | "); also_matches lists other sources it shares phrases with.
    data/processed/english_screenshot_links.tsv + data/processed/primary.pq -> data/processed/screenshot_sources.tsv
And a JSONL file for reading the three texts side by side, one line per matched screenshot (-jsonl, default next to
the TSV): {screenshot: {src, page, site, date, kind, notable, accounts, ocr}, sources: [{url, title, shared,
overlap, text}] (every source with -min-shared phrases, best first), article: {url, title, text}}. The Chinese
article's text is fetched live (src/source_texts.py), each page once; -no-articles leaves it out.

Run as a module from the repo root:
    python -m scripts.match_screenshots_to_sources
    python -m scripts.match_screenshots_to_sources -screenshots /tmp/english_screenshot_links.tsv \\
        -sources /tmp/primary.pq -out /tmp/screenshot_sources.tsv
"""
import argparse
import csv
import json
import os
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from urllib.parse import urlparse

import pandas as pd

from config.paths import ENGLISH_SCREENSHOTS_PATH, PRIMARY_DB_PATH
from src.source_matching import MIN_SHARED, SourceIndex, overlap_spans
from src.source_texts import SourceFetcher

COLUMNS = ['shared', 'source_url', 'source_title', 'kind', 'site', 'page', 'date', 'notable', 'accounts', 'src',
           'also_matches', 'ocr', 'overlap']


def parse_args():
    parser = argparse.ArgumentParser(description='Link English screenshots to the primary sources they show')
    parser.add_argument('-screenshots', default=str(ENGLISH_SCREENSHOTS_PATH))
    parser.add_argument('-sources', default=str(PRIMARY_DB_PATH))
    parser.add_argument('-out', default=os.path.join(os.path.dirname(str(PRIMARY_DB_PATH)), 'screenshot_sources.tsv'))
    parser.add_argument('-min-shared', type=int, default=MIN_SHARED)
    parser.add_argument('-jsonl', default=None, help='default: -out with .jsonl')
    parser.add_argument('-no-articles', action='store_true', help="don't fetch the Chinese articles' text")
    parser.add_argument('-threads', type=int, default=8, help='Chinese articles fetched at once')
    args = parser.parse_args()
    args.jsonl = args.jsonl or os.path.splitext(args.out)[0] + '.jsonl'
    return args


def article_texts(pages, threads):
    """{page: {url, title, text}} of the Chinese articles, fetched live; a page that fails gets empty text."""
    fetcher = SourceFetcher()

    def fetch(page):
        try:
            got = fetcher.page(page)
            return page, {'url': page, 'title': got['title'], 'text': got['text']}
        except Exception as exc:
            return page, {'url': page, 'title': '', 'text': '', 'error': f'{type(exc).__name__}: {exc}'[:200]}
    with ThreadPoolExecutor(threads) as pool:
        return dict(pool.map(fetch, sorted(pages)))


def main():
    args = parse_args()
    store = pd.read_parquet(args.sources, columns=['url', 'status', 'title', 'text'])
    store = store[store.status == 200].fillna('')
    index = SourceIndex(store.to_dict('records'))
    print(f'{len(index.titles)} sources indexed ({len(store) - len(index.titles)} listing pages left out), '
          f'{len(index.index)} distinctive phrases', flush=True)
    with open(args.screenshots, encoding='utf-8', newline='') as f:
        screenshots = list(csv.DictReader(f, delimiter='\t'))
    texts = dict(zip(store.url, store.text))
    rows, records = [], []
    for s in screenshots:
        found = index.match(s['ocr'], args.min_shared)
        if found:
            shot = {k: s.get(k, '') for k in ('src', 'page', 'site', 'date', 'kind', 'notable', 'accounts', 'ocr')}
            records.append({'screenshot': shot,
                            'sources': [{'url': u, 'title': index.titles[u], 'shared': m,
                                         'overlap': overlap_spans(s['ocr'], index.shared_phrases(s['ocr'], u)),
                                         'text': texts[u]} for u, m in found]})
            (url, n), others = found[0], found[1:4]
            rows.append({**{k: s.get(k, '') for k in COLUMNS}, 'shared': n, 'source_url': url,
                         'source_title': index.titles[url], 'also_matches': '; '.join(f'{u} ({m})' for u, m in others),
                         'overlap': ' | '.join(overlap_spans(s['ocr'], index.shared_phrases(s['ocr'], url)))})
    rows.sort(key=lambda r: -r['shared'])
    with open(args.out, 'w', encoding='utf-8', newline='') as f:
        writer = csv.DictWriter(f, COLUMNS, delimiter='\t', extrasaction='ignore')
        writer.writeheader()
        writer.writerows(rows)
    articles = {} if args.no_articles else article_texts({r['screenshot']['page'] for r in records}, args.threads)
    records.sort(key=lambda r: -r['sources'][0]['shared'])
    with open(args.jsonl, 'w', encoding='utf-8') as f:
        for r in records:
            f.write(json.dumps({**r, 'article': articles.get(r['screenshot']['page'], {})}, ensure_ascii=False) + '\n')
    print(f'{len(screenshots)} screenshots -> {len(rows)} matched to a source -> {args.out}, {args.jsonl}')
    print('best match by site of the source:', Counter(urlparse(r['source_url']).netloc for r in rows).most_common(8))
    print('any match (best or not) by site:', Counter(urlparse(src['url']).netloc for r in records
                                                      for src in r['sources']).most_common(8))
    print(f'{len({r["source_url"] for r in rows})} distinct sources; most screenshotted:')
    for url, n in Counter(r['source_url'] for r in rows).most_common(15):
        print(f'  {n:4d}  {url}')
    print('by site:', Counter(r['site'] for r in rows).most_common(8))
    print('match strength (shared phrases):', dict(sorted(Counter(min(r['shared'], 20) for r in rows).items())))
    print(f'spot check: cut -f1,2,13 {args.out} | head    # shared phrases, source, the overlapping passages')


if __name__ == '__main__':
    main()
