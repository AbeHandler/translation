"""
Publication dates of the embedded English CC-NEWS articles (src/news_embeddings.py), for media-storm clustering.
CC-NEWS's warc_date is when the crawler fetched a page, usually soon after publication but sometimes much later;
the publication date comes from the page itself (src/extract_pubdate.py: newspaper4k's URL, JSON-LD and meta
tags, then htmldate on metadata and bylines; not htmldate's extensive search, slow and a guess).

One output file per WARC, a row per embedded article:
    url, warc_date, pubdate (ISO, may be None), pubdate_source (newspaper / htmldate / None),
    date (pubdate's day if found, else warc_date's: the day to cluster on), gap_days (warc_date - pubdate)
"""
import datetime
import os

import pyarrow as pa
import pyarrow.parquet as pq

from src.cc_news import html_rows
from src.extract_pubdate import extract_pubdate

SCHEMA = pa.schema([
    ('url', pa.string()),
    ('warc_date', pa.string()),
    ('pubdate', pa.string()),
    ('pubdate_source', pa.string()),
    ('date', pa.string()),
    ('gap_days', pa.int32()),
])


def day(iso):
    try:
        return datetime.date.fromisoformat((iso or '')[:10])
    except ValueError:
        return None


def article_dates(page):
    """The row for one page ({url, warc_date, html})."""
    html = page['html'].decode('utf-8', errors='replace') if isinstance(page['html'], bytes) else page['html']
    try:
        pubdate, source = extract_pubdate(html, page['url'], extensive=False)
    except Exception:  # garbled pages
        pubdate, source = None, None
    published, fetched = day(pubdate), day(page['warc_date'])
    return {'url': page['url'], 'warc_date': page['warc_date'], 'pubdate': pubdate, 'pubdate_source': source,
            'date': (published or fetched).isoformat() if (published or fetched) else None,
            'gap_days': (fetched - published).days if published and fetched else None}


def date_file(embeddings_path, html_dir, out_path):
    """Dates for the articles of one embeddings file, from the HTML of the same WARC. Written via .part, so a
    partial file never looks done. Returns counts."""
    urls = set(pq.read_table(embeddings_path, columns=['url']).column('url').to_pylist())
    html_path = os.path.join(html_dir, os.path.basename(embeddings_path))
    rows = [article_dates(page) for page in html_rows(html_path, urls, columns=('url', 'warc_date', 'html'))]
    pq.write_table(pa.Table.from_pylist(rows, SCHEMA), out_path + '.part', compression='zstd')
    os.rename(out_path + '.part', out_path)
    return {'articles': len(rows), 'with_pubdate': sum(r['pubdate'] is not None for r in rows)}
