#!/usr/bin/env python
"""
Build model1's feature matrix (docs/model1.md): mine candidate pairs (src/features/candidates.py; for now the
linked pairs only), then each candidate's features (src/features/pairs.py): link, quote_link (the link in
quotation marks, src/features/quoting.py; needs the English pages' HTML), copy (src/features/copying.py),
embedding similarity (LaBSE, title + start of text) and date gap.
    -links     cleaned en->zh links (scripts/clean_en_zh_links.py): srcpage, url
    -en-docs   English documents, JSONL {url, title, body or text, pubdate}
    -zh-docs   Chinese documents (zh_docs): url, title, text, pubdate, is_document
    -en-html-dir  optional: the English pages' HTML as <sha1 of url>.html (e.g. $TMP/airules/html)
    -labels    optional CSV doc_en, doc_zh, y
    -> -out    CSV doc_en, doc_zh, link, quote_link, copy, similarity, date_gap, y, runs (copied Chinese runs)

Run as a module from the repo root:
    python -m scripts.build_transmission_pairs -en-docs /tmp/airules/articles.jsonl -zh-docs /tmp/zh_docs.jsonl \\
        -links /tmp/news_en_zh_links_clean.jsonl -en-html-dir /tmp/airules/html -out /tmp/transmission_pairs.csv
"""
import argparse
import datetime
import hashlib
import json
import os

from config.paths import NEWS_EN_ZH_LINKS_PATH, TRANSMISSION_PAIRS_PATH, ZH_DOCS_PATH
from src.features.candidates import mine_candidates
from src.features.copying import CopyIndex
from src.features.pairs import feature_matrix, read_labels, write_pairs
from src.features.quoting import link_quoted
from src.restatement.pages import citing_paragraphs

MODEL = 'sentence-transformers/LaBSE'
LEAD_CHARS = 500


def parse_args():
    parser = argparse.ArgumentParser(description="Build model1's feature matrix of candidate pairs")
    parser.add_argument('-links', default=str(NEWS_EN_ZH_LINKS_PATH).replace('.jsonl', '_clean.jsonl'))
    parser.add_argument('-en-docs', required=True, help='JSONL {url, title, body or text, pubdate}')
    parser.add_argument('-zh-docs', default=str(ZH_DOCS_PATH))
    parser.add_argument('-en-html-dir', default='', help="English pages' HTML, <sha1 of url>.html")
    parser.add_argument('-labels', default='', help='CSV doc_en, doc_zh, y')
    parser.add_argument('-max-df', type=int, default=20,
                        help='a Chinese run found in more Chinese documents than this is a common term, not a copy')
    parser.add_argument('-out', default=str(TRANSMISSION_PAIRS_PATH))
    return parser.parse_args()


def read_jsonl(path):
    with open(path, encoding='utf-8') as f:
        return [json.loads(line) for line in f]


def day(date):
    try:
        return datetime.date.fromisoformat((date or '')[:10]).toordinal()
    except ValueError:
        return None


def embed(docs, text_key):
    from sentence_transformers import SentenceTransformer  # loaded only here
    model = SentenceTransformer(MODEL, device='cpu')
    texts = [f"{d.get('title') or ''}\n{(d.get(text_key(d)) or '')[:LEAD_CHARS]}" for d in docs]
    return dict(zip([d['url'] for d in docs], model.encode(texts, normalize_embeddings=True, batch_size=32)))


def quoted_links(links, html_dir):
    """{(en, zh): 1/0/-1}: whether each link is in quotation marks, from the English page's HTML if it's there."""
    out = {}
    for en, zh in links:
        path = os.path.join(html_dir, hashlib.sha1(en.encode()).hexdigest() + '.html') if html_dir else ''
        if path and os.path.exists(path):
            with open(path, encoding='utf-8') as f:
                html = f.read()
            out[(en, zh)] = link_quoted(citing_paragraphs(html, en, zh)) if html.strip() else -1
    return out


def main():
    args = parse_args()
    en_docs = {d['url']: d for d in read_jsonl(args.en_docs) if d.get('body') or d.get('text')}
    zh_docs = {d['url']: d for d in read_jsonl(args.zh_docs) if d.get('is_document')}
    links = {(r['srcpage'], r['url']) for r in read_jsonl(args.links)
             if r['srcpage'] in en_docs and r['url'] in zh_docs}
    pairs = mine_candidates(links)

    en_texts = {u: (d.get('title') or '') + '\n' + (d.get('body') or d.get('text')) for u, d in en_docs.items()}
    zh_texts = {u: (d.get('title') or '') + '\n' + d['text'] for u, d in zh_docs.items()}
    index = CopyIndex(zh_texts, args.max_df)
    copies = {en: index.copied(en_texts[en]) for en in {en for en, _ in pairs}}
    en_used = [en_docs[u] for u in sorted({en for en, _ in pairs})]
    zh_used = [zh_docs[u] for u in sorted({zh for _, zh in pairs})]
    vectors = {**embed(en_used, lambda d: 'body' if d.get('body') else 'text'), **embed(zh_used, lambda d: 'text')}
    days = {u: day(d.get('pubdate')) for u, d in {**en_docs, **zh_docs}.items()}
    quoted = quoted_links(links, args.en_html_dir)
    X = feature_matrix(pairs, links, quoted, copies, vectors, vectors, days, days)

    labels = read_labels(args.labels) if args.labels else {}
    os.makedirs(os.path.dirname(os.path.abspath(args.out)), exist_ok=True)
    runs = ['|'.join(sorted(copies[en].get(zh, []))) for en, zh in pairs]
    write_pairs(args.out, pairs, X, {'y': [labels.get(p, '') for p in pairs], 'runs': runs})
    print(f'{len(pairs)} candidate pairs ({len(links)} linked) from {len(en_used)} English and {len(zh_used)} '
          f'Chinese documents -> {args.out}')
    print(f'  quoted links {int((X[:, 1] == 1).sum())} (of {int((X[:, 1] >= 0).sum())} with HTML), '
          f'copying {int(X[:, 2].sum())}, labelled {sum(p in labels for p in pairs)}')


if __name__ == '__main__':
    main()
