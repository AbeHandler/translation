#!/usr/bin/env python
"""
The primary-source documents behind the English media storms (src/seed_documents.py): each storm's cited
documents (scripts/media_storms.py -step seeds) that are not news coverage, one TSV row per document, most covered
first, with how much English coverage cited it:
    document href kind en_articles en_outlets storms top_share peak storm_title
en_articles: storm articles linking to it (summed over its storms); top_share: the largest share of one storm's
articles citing it.
    data/interim/media_storms/ -> data/processed/seed_documents.tsv

Run as a module from the repo root:
    python -m scripts.export_seed_documents
"""
import argparse
import csv
import glob
import json
import os

import pyarrow.parquet as pq

from config.paths import MEDIA_STORMS_DIR, NEWS_EN_ZH_LINKS_PATH
from src.seed_documents import is_primary, source_kind

COLUMNS = ['document', 'href', 'kind', 'en_articles', 'en_outlets', 'storms', 'top_share', 'peak', 'storm_title']


def parse_args():
    parser = argparse.ArgumentParser(description='Export the primary-source documents behind the media storms')
    parser.add_argument('-storms-dir', default=str(MEDIA_STORMS_DIR))
    parser.add_argument('-min-articles', type=int, default=5, help='storm articles citing it, at least')
    parser.add_argument('-out', default=os.path.join(os.path.dirname(str(NEWS_EN_ZH_LINKS_PATH)), 'seed_documents.tsv'))
    return parser.parse_args()


def news_outlets(days_dir):
    """The registered domains of every article in the storms' corpus: news outlets, so not primary sources."""
    outlets = set()
    for path in glob.glob(os.path.join(days_dir, '*', '*.parquet')):
        outlets.update(pq.read_table(path, columns=['outlet']).column('outlet').to_pylist())
    return outlets


def seed_documents(storms, seeds, outlets, min_articles):
    """{document key: row} for the primary-source documents the storms cite."""
    docs = {}
    for cluster, row in seeds.items():
        if row.get('template'):
            continue
        storm = storms[cluster]
        for d in row['seeds']:
            if d['articles'] < min_articles or not is_primary(d['document'], outlets):
                continue
            doc = docs.setdefault(d['document'], {
                'document': d['document'], 'href': d['href'], 'kind': source_kind(d['document']), 'en_articles': 0,
                'en_outlets': 0, 'storms': 0, 'top_share': 0.0, 'peak': storm['peak'], 'storm_title': storm['title']})
            doc['en_articles'] += d['articles']
            doc['en_outlets'] = max(doc['en_outlets'], d['outlets'])
            doc['storms'] += 1
            if d['share'] > doc['top_share']:
                doc.update(top_share=d['share'], peak=storm['peak'], storm_title=storm['title'])
    return docs


def main():
    args = parse_args()
    with open(os.path.join(args.storms_dir, 'storms.jsonl'), encoding='utf-8') as f:
        storms = {s['cluster']: s for s in map(json.loads, f)}
    with open(os.path.join(args.storms_dir, 'storm_seeds.jsonl'), encoding='utf-8') as f:
        seeds = {s['cluster']: s for s in map(json.loads, f)}
    outlets = news_outlets(os.path.join(args.storms_dir, 'days'))
    print(f'{len(storms)} storms, {len(outlets)} news outlets', flush=True)
    docs = seed_documents(storms, seeds, outlets, args.min_articles)
    rows = sorted(docs.values(), key=lambda d: -d['en_articles'])
    with open(args.out + '.part', 'w', encoding='utf-8', newline='') as f:
        writer = csv.DictWriter(f, COLUMNS, delimiter='\t')
        writer.writeheader()
        writer.writerows(rows)
    os.rename(args.out + '.part', args.out)
    print(f'{len(rows)} primary-source documents -> {args.out}')
    for r in rows[:15]:
        print(f"  {r['en_articles']:5d}  {r['kind']:14} {r['href'][:90]}")
    print(f'spot check: cut -f2,3,4,7 {args.out} | head -20')


if __name__ == '__main__':
    main()
