#!/usr/bin/env python
"""
For each (English article -> Chinese page) pair, how the article restates the page: its citing paragraph's
sentences aligned with the page's sentences (src/restatement), labelled translation / paraphrase / neither.

Input: a JSONL of link results with srcpage (the English article) and url (the Chinese page), e.g.
    jq -c 'select(.language == "zh")' data/processed/news_link_languages.jsonl > /tmp/zh_pairs.jsonl
Pages are fetched live (-cache-dir keeps them, so reruns don't refetch). Output: one line per pair.

Run as a module from the repo root:
    python -m scripts.find_restatements -pairs /tmp/zh_pairs.jsonl -out /tmp/restatements.jsonl
"""
import argparse
import hashlib
import json
import os

import httpx
from sentence_transformers import SentenceTransformer

from src.link_language.fetch import HEADERS, decode
from src.restatement.align import MODEL, Aligner, label
from src.restatement.pages import anchor_sentence, chinese_sentences, citing_paragraphs, english_sentences, main_text


def parse_args():
    parser = argparse.ArgumentParser(description='Translation / paraphrase / neither for English->Chinese links')
    parser.add_argument('-pairs', required=True, help='JSONL with srcpage and url')
    parser.add_argument('-out', required=True)
    parser.add_argument('-cache-dir', default='/tmp/restatement_pages', help='fetched pages, kept for reruns')
    parser.add_argument('-model', default=MODEL)
    return parser.parse_args()


def fetch(url, cache_dir, client):
    """The page's HTML, from the cache or fetched (and cached)."""
    path = os.path.join(cache_dir, hashlib.sha1(url.encode()).hexdigest() + '.html')
    if not os.path.exists(path):
        response = client.get(url, headers=HEADERS, follow_redirects=True, timeout=30)
        response.raise_for_status()
        with open(path, 'w', encoding='utf-8') as f:
            f.write(decode(response.content, response.charset_encoding))
    with open(path, encoding='utf-8') as f:
        return f.read()


def restatement(pair, aligner, cache_dir, client):
    en_html = fetch(pair['srcpage'], cache_dir, client)
    paragraphs = citing_paragraphs(en_html, pair['srcpage'], pair['url'])
    zh = chinese_sentences(main_text(fetch(pair['url'], cache_dir, client)))
    en = [s for p in paragraphs for s in english_sentences(p['paragraph'])]
    rows, best = aligner.align(en, zh)
    anchors = {anchor_sentence(p['paragraph'], p['anchor_text']) for p in paragraphs} - {None}
    anchor_best = max((r['matches'][0]['score'] for r in rows if r['en'] in anchors), default=0.0)
    if not rows:
        verdict = 'no_citing_text' if not paragraphs else 'no_chinese_text'
    else:
        verdict = label(best)
    return {'srcpage': pair['srcpage'], 'url': pair['url'], 'label': verdict, 'best_score': round(best, 3),
            'anchor_label': label(anchor_best) if anchors and rows else None, 'anchor_score': round(anchor_best, 3),
            'anchor_sentences': sorted(anchors), 'citing': paragraphs, 'n_zh_sentences': len(zh), 'alignment': rows}


def main():
    args = parse_args()
    os.makedirs(args.cache_dir, exist_ok=True)
    aligner = Aligner(SentenceTransformer(args.model, device='cpu'))
    with open(args.pairs, encoding='utf-8') as f:
        pairs = list({(p['srcpage'], p['url']): p for p in map(json.loads, f)}.values())
    client = httpx.Client()
    with open(args.out, 'w', encoding='utf-8') as out:
        for n, pair in enumerate(pairs, 1):
            try:
                row = restatement(pair, aligner, args.cache_dir, client)
            except Exception as exc:
                row = {'srcpage': pair['srcpage'], 'url': pair['url'], 'label': 'error',
                       'error': f'{type(exc).__name__}: {exc}'[:300]}
            out.write(json.dumps(row, ensure_ascii=False) + '\n')
            print(f"{n}/{len(pairs)} {row['label']:15} {row.get('best_score', '')}  anchor: "
                  f"{row.get('anchor_label')} {row.get('anchor_score', '')}  {pair['url'][:60]}", flush=True)


if __name__ == '__main__':
    main()
