#!/usr/bin/env python
"""
Daily 2026-10-01: the English pages that link to the CAC's Interim Measures for Generative AI Services
(生成式人工智能服务管理暂行办法, https://www.cac.gov.cn/2023-07/13/c_1690898327029107.htm): fetch each one and
pull out its article body and publication date.
    -links (cleaned en->zh links) -> $TMP/airules/html/<sha1 of url>.html   the pages, fetched once
                                  -> $TMP/airules/articles.jsonl          {url, linked_url, status, title,
                                                                           pubdate, pubdate_source, body,
                                                                           body_source, error}
Pages are fetched in random order and skipped when already on disk (the HTTP status is kept in <sha1>.html.json),
so a rerun only fetches what's missing. The body comes from the page's JSON-LD articleBody (CNN, AP), else
newspaper4k, else readability. Error pages (404, 429) get an `error` and no body.

Run from the repo root:
    python -m scripts.dailies.s20261001
    python -m scripts.dailies.s20261001 -links /tmp/news_en_zh_links_clean.jsonl
"""
import argparse
import hashlib
import json
import os
import random

import httpx
import lxml.html

from newspaper import Article

from config.paths import NEWS_EN_ZH_LINKS_PATH
from src.cc_news import readable_article
from src.extract_pubdate import extract_pubdate
from src.link_language.fetch import fetch_html

TARGET = '/2023-07/13/c_1690898327029107.htm'  # the CAC page's path: matches its http, https and translate.goog URLs


def parse_args():
    clean = str(NEWS_EN_ZH_LINKS_PATH).replace('.jsonl', '_clean.jsonl')
    parser = argparse.ArgumentParser(description='Fetch the English pages linking to the CAC generative-AI rules')
    parser.add_argument('-links', default=clean, help='cleaned en->zh links (scripts/clean_en_zh_links.py)')
    parser.add_argument('-target', default=TARGET, help='part of the Chinese URL to look for')
    parser.add_argument('-out-dir', default='', help='default $TMP/airules')
    return parser.parse_args()


def inbound(links_path, target):
    """{english url: the Chinese URL it links to} for the links to target (the translate.goog form too)."""
    found = {}
    with open(links_path, encoding='utf-8') as f:
        for line in f:
            row = json.loads(line)
            if target in row['url']:
                found[row['srcpage']] = row['url']
    return found


MIN_BODY_CHARS = 200


def json_ld_article(html):
    """(articleBody, datePublished) from the page's schema.org NewsArticle JSON-LD (CNN, AP, many others keep
    the full text there), or ('', None)."""
    doc = lxml.html.fromstring(html)
    for script in doc.xpath('//script[@type="application/ld+json"]/text()'):
        try:
            data = json.loads(script)
        except ValueError:
            continue
        items = data if isinstance(data, list) else data.get('@graph', [data]) if isinstance(data, dict) else []
        for item in items:
            if isinstance(item, dict) and item.get('articleBody'):
                return ' '.join(str(item['articleBody']).split()), item.get('datePublished')
    return '', None


def newspaper_article(html, url):
    article = Article(url, language='en', fetch_images=False)
    article.download(input_html=html)
    article.parse()
    return article.title, article.text


def article(html, url):
    """{title, body, body_source, pubdate, pubdate_source}: the body from JSON-LD, else newspaper4k, else
    readability, whichever first has MIN_BODY_CHARS; the date from JSON-LD, else the date extractor."""
    title, body, source = '', '', None
    ld_body, ld_date = json_ld_article(html)
    candidates = [('json_ld', lambda: ('', ld_body)), ('newspaper', lambda: newspaper_article(html, url)),
                  ('readability', lambda: (readable_article(html)[0],
                                           ' '.join(readable_article(html)[1].text_content().split())))]
    for name, extract in candidates:
        try:
            found_title, text = extract()
        except Exception:
            continue
        title = title or found_title
        if len(text) >= MIN_BODY_CHARS:
            body, source = text, name
            break
    pubdate, pubdate_source = (ld_date, 'json_ld') if ld_date else extract_pubdate(html, url)
    if not title:
        title = ' '.join((lxml.html.fromstring(html).findtext('.//title') or '').split())
    return {'title': title, 'body': body, 'body_source': source, 'pubdate': pubdate, 'pubdate_source': pubdate_source}


def main():
    args = parse_args()
    out_dir = args.out_dir or os.path.join(os.environ['TMP'], 'airules')
    html_dir = os.path.join(out_dir, 'html')
    os.makedirs(html_dir, exist_ok=True)
    pages = inbound(args.links, args.target)
    print(f'{len(pages)} English pages link to {args.target}')
    urls = sorted(pages)
    random.shuffle(urls)
    client = httpx.Client()
    rows = []
    for n, url in enumerate(urls, 1):
        path = os.path.join(html_dir, hashlib.sha1(url.encode()).hexdigest() + '.html')
        row = {'url': url, 'linked_url': pages[url]}
        try:
            if not os.path.exists(path):
                page = fetch_html(url, client)
                with open(path + '.json', 'w') as f:  # the fetch's status, kept beside the page
                    json.dump({'status': page.status, 'final_url': page.final_url}, f)
                with open(path + '.part', 'w', encoding='utf-8') as f:
                    f.write(page.html)
                os.rename(path + '.part', path)
            meta = json.load(open(path + '.json')) if os.path.exists(path + '.json') else {}
            row.update(meta)
            with open(path, encoding='utf-8') as f:
                html = f.read()
            if meta.get('status', 200) != 200:
                row['error'] = f"HTTP {meta['status']}"
            elif not html:
                row['error'] = 'no HTML'
            else:
                row.update(article(html, url))
        except Exception as exc:
            row['error'] = f'{type(exc).__name__}: {exc}'[:200]
        rows.append(row)
        print(f"{n}/{len(urls)} {row.get('pubdate') or '-':25.25} {len(row.get('body', '')):6d} chars  {url[:80]}",
              flush=True)
    out = os.path.join(out_dir, 'articles.jsonl')
    with open(out, 'w', encoding='utf-8') as f:
        f.writelines(json.dumps(row, ensure_ascii=False) + '\n' for row in rows)
    print(f'\n{len(rows)} articles -> {out}; {sum("error" in r for r in rows)} errors, '
          f'{sum(not r.get("body") for r in rows)} without a body')
    print('Spot checks:')
    print(f"  jq -r '[.pubdate, .url] | @tsv' {out} | sort")
    print(f"  jq -r 'select(.url | contains(\"cnn.com/2023/07/14\")) | .body' {out} | head -40")


if __name__ == '__main__':
    main()
