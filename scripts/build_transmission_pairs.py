#!/usr/bin/env python
"""
Build model1's pair table (src/data/transmission_pairs.py, docs/model1.md) without the full English x Chinese
table: one row per linked, copying or labelled pair, plus one background row counting every other (English,
Chinese) pair.
    -links     cleaned en->zh links (scripts/clean_en_zh_links.py): srcpage, url
    -en-docs   English documents, JSONL {url, title, body or text}
    -zh-docs   Chinese documents (zh_docs): url, title, text, is_document
    -labels    optional CSV doc_en, doc_zh, y
    -> -out    CSV doc_en, doc_zh, L, c, y, w, runs (the copied Chinese runs)

Run as a module from the repo root:
    python -m scripts.build_transmission_pairs -en-docs /tmp/airules/articles.jsonl -zh-docs /tmp/zh_docs.jsonl \\
        -links /tmp/news_en_zh_links_clean.jsonl -out /tmp/transmission_pairs.csv
"""
import argparse
import json
import os

from config.paths import NEWS_EN_ZH_LINKS_PATH, TRANSMISSION_PAIRS_PATH, ZH_DOCS_PATH
from src.data.transmission_pairs import CopyIndex, build_pairs, read_labels, write_pairs


def parse_args():
    parser = argparse.ArgumentParser(description="Build model1's (English doc, Chinese doc) pair table")
    parser.add_argument('-links', default=str(NEWS_EN_ZH_LINKS_PATH).replace('.jsonl', '_clean.jsonl'))
    parser.add_argument('-en-docs', required=True, help='JSONL {url, title, body or text}')
    parser.add_argument('-zh-docs', default=str(ZH_DOCS_PATH))
    parser.add_argument('-labels', default='', help='CSV doc_en, doc_zh, y')
    parser.add_argument('-max-df', type=int, default=20,
                        help='a Chinese run found in more Chinese documents than this is a common term, not a copy')
    parser.add_argument('-out', default=str(TRANSMISSION_PAIRS_PATH))
    return parser.parse_args()


def read_jsonl(path):
    with open(path, encoding='utf-8') as f:
        return [json.loads(line) for line in f]


def main():
    args = parse_args()
    en_docs = [d for d in read_jsonl(args.en_docs) if d.get('body') or d.get('text')]
    zh_docs = [d for d in read_jsonl(args.zh_docs) if d.get('is_document')]
    en_texts = {d['url']: (d.get('title') or '') + '\n' + (d.get('body') or d.get('text')) for d in en_docs}
    zh_texts = {d['url']: (d.get('title') or '') + '\n' + d['text'] for d in zh_docs}
    links = [(r['srcpage'], r['url']) for r in read_jsonl(args.links)
             if r['srcpage'] in en_texts and r['url'] in zh_texts]
    n_universe = len(en_texts) * len(zh_texts)

    rows = build_pairs(links, en_texts, CopyIndex(zh_texts, args.max_df),
                       read_labels(args.labels) if args.labels else {}, n_universe)
    os.makedirs(os.path.dirname(os.path.abspath(args.out)), exist_ok=True)
    write_pairs(rows, args.out)
    pairs = rows[:-1]
    print(f'{len(en_texts)} English docs x {len(zh_texts)} Chinese documents = {n_universe:,} pairs')
    print(f"{len(pairs)} explicit pairs: linked {sum(r['L'] for r in pairs)}, copying {sum(r['c'] for r in pairs)} "
          f"({sum(r['L'] * r['c'] for r in pairs)} both), labelled {sum(r['y'] != '' for r in pairs)}; "
          f"background row weight {rows[-1]['w']:,} -> {args.out}")
    print('Spot checks:')
    print(f"  python -c \"import csv; [print(r['runs'], r['doc_en'][:50], r['doc_zh'][:50]) "
          f"for r in csv.DictReader(open('{args.out}')) if r['c'] == '1']\"")


if __name__ == '__main__':
    main()
