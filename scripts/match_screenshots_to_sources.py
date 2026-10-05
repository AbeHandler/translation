#!/usr/bin/env python
"""
Link the English screenshots in the Chinese crawls to the primary sources they show (src/source_matching.py):
each screenshot's OCR text against every fetched source in the store, kept if they share -min-shared five-word
phrases. One row per matched screenshot, strongest first:
    shared, source_url, source_title, kind, site, page, date, notable, accounts, src, ocr
shared is the number of five-word phrases in common; also_matches lists other sources it shares phrases with.
    data/processed/english_screenshot_links.tsv + data/processed/primary.pq -> data/processed/screenshot_sources.tsv

Run as a module from the repo root:
    python -m scripts.match_screenshots_to_sources
    python -m scripts.match_screenshots_to_sources -screenshots /tmp/english_screenshot_links.tsv \\
        -sources /tmp/primary.pq -out /tmp/screenshot_sources.tsv
"""
import argparse
import csv
import os
from collections import Counter

import pandas as pd

from config.paths import ENGLISH_SCREENSHOTS_PATH, PRIMARY_DB_PATH
from src.source_matching import MIN_SHARED, SourceIndex

COLUMNS = ['shared', 'source_url', 'source_title', 'kind', 'site', 'page', 'date', 'notable', 'accounts', 'src',
           'also_matches', 'ocr']


def parse_args():
    parser = argparse.ArgumentParser(description='Link English screenshots to the primary sources they show')
    parser.add_argument('-screenshots', default=str(ENGLISH_SCREENSHOTS_PATH))
    parser.add_argument('-sources', default=str(PRIMARY_DB_PATH))
    parser.add_argument('-out', default=os.path.join(os.path.dirname(str(PRIMARY_DB_PATH)), 'screenshot_sources.tsv'))
    parser.add_argument('-min-shared', type=int, default=MIN_SHARED)
    return parser.parse_args()


def main():
    args = parse_args()
    store = pd.read_parquet(args.sources, columns=['url', 'status', 'title', 'text'])
    store = store[store.status == 200].fillna('')
    index = SourceIndex(store.to_dict('records'))
    print(f'{len(index.titles)} sources indexed ({len(store) - len(index.titles)} listing pages left out), '
          f'{len(index.index)} distinctive phrases', flush=True)
    with open(args.screenshots, encoding='utf-8', newline='') as f:
        screenshots = list(csv.DictReader(f, delimiter='\t'))
    rows = []
    for s in screenshots:
        found = index.match(s['ocr'], args.min_shared)
        if found:
            (url, n), others = found[0], found[1:4]
            rows.append({**{k: s.get(k, '') for k in COLUMNS}, 'shared': n, 'source_url': url,
                         'source_title': index.titles[url], 'also_matches': '; '.join(f'{u} ({m})' for u, m in others)})
    rows.sort(key=lambda r: -r['shared'])
    with open(args.out, 'w', encoding='utf-8', newline='') as f:
        writer = csv.DictWriter(f, COLUMNS, delimiter='\t', extrasaction='ignore')
        writer.writeheader()
        writer.writerows(rows)
    print(f'{len(screenshots)} screenshots -> {len(rows)} matched to a source -> {args.out}')
    print(f'{len({r["source_url"] for r in rows})} distinct sources; most screenshotted:')
    for url, n in Counter(r['source_url'] for r in rows).most_common(15):
        print(f'  {n:4d}  {url}')
    print('by site:', Counter(r['site'] for r in rows).most_common(8))
    print('match strength (shared phrases):', dict(sorted(Counter(min(r['shared'], 20) for r in rows).items())))
    print(f'spot check: cut -f1,2,5,12 {args.out} | awk -F"\\t" \'$1 <= 4\' | head    # the weakest matches')


if __name__ == '__main__':
    main()
