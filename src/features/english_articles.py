"""
The English side of the candidate pairs, from what the CC-NEWS crawl stored: each article's HTML is in
data/interim/cc_html/<warc>.parquet, and the cleaning step's source cache (scripts/clean_en_zh_links.py) records
which WARC (links file) every English source came from. Only the row groups holding the wanted articles are read.
"""
import os
from collections import defaultdict

import lxml.html

from src.cc_news import html_rows, readable_article


def paragraphs_text(element):
    return '\n'.join(' '.join(p.text_content().split()) for p in element.iter('p') if p.text_content().strip())


def article_text(html):
    """(title, body text) by readability, falling back to all the page's paragraphs when readability finds none
    (short articles); ('', '') for pages that can't be parsed."""
    try:
        title, body = readable_article(html)
        text = paragraphs_text(body) or ' '.join(body.text_content().split())
        return title, text or paragraphs_text(lxml.html.fromstring(html))
    except Exception:
        return '', ''


def articles_from_cc_html(links_files, html_dir):
    """{url: {url, title, text, pubdate, html}} for the articles in links_files ({url: links file name}); the date
    is the WARC record's (CC-NEWS fetches articles soon after publication). Articles whose file is missing are
    left out."""
    by_file = defaultdict(set)
    for url, links_file in links_files.items():
        if links_file:
            by_file[links_file].add(url)
    out = {}
    for links_file, urls in sorted(by_file.items()):
        path = os.path.join(html_dir, links_file.removesuffix('.jsonl') + '.parquet')
        if not os.path.exists(path):
            continue
        for row in html_rows(path, urls, columns=('url', 'warc_date', 'html')):
            html = row['html'].decode('utf-8', errors='replace') if isinstance(row['html'], bytes) else row['html']
            title, text = article_text(html)
            out[row['url']] = {'url': row['url'], 'title': title, 'text': text,
                               'pubdate': (row['warc_date'] or '')[:10], 'html': html}
    return out
