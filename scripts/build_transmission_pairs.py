#!/usr/bin/env python
"""
Build model1's pair table (src/transmission/pairs.py, docs/model1.md): every English document's linked Chinese
documents plus its -k nearest Chinese documents by LaBSE embedding (title + start of the text), with L (link),
c (copied Chinese string) and y (hand labels, if -labels is given).
    -links     cleaned en->zh links (scripts/clean_en_zh_links.py): srcpage, url
    -en-docs   English documents, JSONL {url, title, body or text}
    -zh-docs   Chinese documents (scripts/zh_docs_queue.py + process_queue.sh zh_docs): url, title, text
    -labels    optional CSV doc_en, doc_zh, y
    -> -out    CSV doc_en, doc_zh, L, c, y
Only Chinese pages that are documents (is_document) are candidates.

Run as a module from the repo root:
    python -m scripts.build_transmission_pairs -en-docs /tmp/airules/articles.jsonl -zh-docs /tmp/zh_docs.jsonl \\
        -links /tmp/news_en_zh_links_clean.jsonl -out /tmp/transmission_pairs.csv
"""
import argparse
import json
import os

from config.paths import NEWS_EN_ZH_LINKS_PATH, TRANSMISSION_PAIRS_PATH, ZH_DOCS_PATH
from src.transmission.pairs import build_pairs, nearest, read_labels, write_pairs

MODEL = 'sentence-transformers/LaBSE'
LEAD_CHARS = 500


def parse_args():
    parser = argparse.ArgumentParser(description="Build model1's (English doc, Chinese doc) pair table")
    parser.add_argument('-links', default=str(NEWS_EN_ZH_LINKS_PATH).replace('.jsonl', '_clean.jsonl'))
    parser.add_argument('-en-docs', required=True, help='JSONL {url, title, body or text}')
    parser.add_argument('-zh-docs', default=str(ZH_DOCS_PATH))
    parser.add_argument('-labels', default='', help='CSV doc_en, doc_zh, y')
    parser.add_argument('-k', type=int, default=5, help='nearest Chinese documents per English document')
    parser.add_argument('-out', default=str(TRANSMISSION_PAIRS_PATH))
    return parser.parse_args()


def read_jsonl(path):
    with open(path, encoding='utf-8') as f:
        return [json.loads(line) for line in f]


def lead(doc, text_key):
    return f"{doc.get('title') or ''}\n{(doc.get(text_key) or '')[:LEAD_CHARS]}"


def main():
    args = parse_args()
    en_docs = [d for d in read_jsonl(args.en_docs) if d.get('body') or d.get('text')]
    zh_docs = [d for d in read_jsonl(args.zh_docs) if d.get('is_document')]
    en_texts = {d['url']: (d.get('title') or '') + '\n' + (d.get('body') or d.get('text')) for d in en_docs}
    zh_texts = {d['url']: (d.get('title') or '') + '\n' + d['text'] for d in zh_docs}
    links = [(r['srcpage'], r['url']) for r in read_jsonl(args.links) if r['srcpage'] in en_texts]

    neighbours = {}
    if args.k:
        from sentence_transformers import SentenceTransformer  # only needed for the neighbours
        model = SentenceTransformer(MODEL, device='cpu')
        en_vecs = model.encode([lead(d, 'body' if d.get('body') else 'text') for d in en_docs],
                               normalize_embeddings=True, batch_size=32)
        zh_vecs = model.encode([lead(d, 'text') for d in zh_docs], normalize_embeddings=True, batch_size=32)
        for d, idx in zip(en_docs, nearest(en_vecs, zh_vecs, args.k)):
            neighbours[d['url']] = [zh_docs[j]['url'] for j in idx]

    labels = read_labels(args.labels) if args.labels else {}
    rows = build_pairs(links, neighbours, en_texts, zh_texts, labels)
    os.makedirs(os.path.dirname(os.path.abspath(args.out)), exist_ok=True)
    write_pairs(rows, args.out)
    n = len(rows)
    print(f'{len(en_texts)} English docs, {len(zh_texts)} Chinese documents -> {n} pairs in {args.out}')
    print(f"  linked {sum(r['L'] for r in rows)}, copying {sum(r['c'] for r in rows)}, "
          f"labelled {sum(r['y'] != '' for r in rows)}, linked and copying {sum(r['L'] * r['c'] for r in rows)}")
    print('Spot checks:')
    print(f"  awk -F, '$4 == 1' {args.out} | head      # pairs with copied Chinese text")


if __name__ == '__main__':
    main()
