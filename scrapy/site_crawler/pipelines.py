"""Saves each crawled HTML page's raw HTML as zstd-compressed Parquet, in the same format as the CC-NEWS
pipeline (src/cc_news.py ArticleHtmlArchiver: url, language, warc_date, content_type, record_id, html), so
both go through the same parsing and embedding later. warc_date is the crawl time; record_id is a new
urn:uuid, as in a WARC.

Writes <HTML_DIR>/part-<time>-<n>.parquet every ROWS_PER_FILE pages and when the crawl stops, each via
.part so a partial file never looks complete. HTML_DIR is a scrapy setting (-s HTML_DIR=...).
"""
import datetime
import logging
import os
import time
import uuid

import pyarrow as pa
import pyarrow.parquet as pq

from src.cc_news import ArticleHtmlArchiver, NewsPleaseLanguage

logger = logging.getLogger(__name__)


class HtmlParquetPipeline:
    SCHEMA = ArticleHtmlArchiver.SCHEMA
    ROWS_PER_FILE = 1000  # small files: a crash (not the clean 11.5h stop) loses at most this many pages

    def __init__(self, html_dir):
        self.html_dir = html_dir
        self.rows = []
        self.n_files = 0
        self.run_id = time.strftime('%Y%m%dT%H%M%S')  # keeps a resumed crawl's files apart from earlier runs'
        self.language = NewsPleaseLanguage()

    @classmethod
    def from_crawler(cls, crawler):
        html_dir = crawler.settings.get('HTML_DIR')
        if not html_dir:
            raise ValueError('set HTML_DIR, e.g. -s HTML_DIR=data/interim/site_crawls/<domain>/html')
        os.makedirs(html_dir, exist_ok=True)
        return cls(html_dir)

    def process_item(self, item, spider):
        """Takes the page's html, content_type and is_html off the item (so they stay out of pages.jsonl).
        is_html is scrapy's judgement, which also looks at the body: some servers (zhidx) omit Content-Type."""
        html = item.pop('html')
        content_type = item.pop('content_type')
        if not item.pop('is_html'):
            spider.crawler.stats.inc_value('html_parquet/skipped_not_html')
            logger.info('not saving HTML for %s: Content-Type %r', item['url'], content_type)
            return item
        self.rows.append(self.row(item, html, content_type))
        spider.crawler.stats.inc_value('html_parquet/rows')
        if len(self.rows) >= self.ROWS_PER_FILE:
            self.write()
        return item

    def close_spider(self, spider):
        self.write()

    def row(self, item, html, content_type):
        crawled_at = datetime.datetime.fromisoformat(item['crawled_at'])
        return {'url': item['url'], 'language': self.language_of(html),
                'warc_date': crawled_at.strftime('%Y-%m-%dT%H:%M:%SZ'), 'content_type': content_type,
                'record_id': f'<urn:uuid:{uuid.uuid4()}>', 'html': html}

    def language_of(self, html):
        try:
            return self.language(html)
        except Exception as exc:  # empty/garbled pages; CC-NEWS drops these, here the row keeps language None
            logger.debug('language failed: %s', exc)
            return None

    def write(self):
        if not self.rows:
            return
        path = os.path.join(self.html_dir, f'part-{self.run_id}-{self.n_files:05d}.parquet')
        pq.write_table(pa.Table.from_pylist(self.rows, self.SCHEMA), path + '.part', compression='zstd')
        os.rename(path + '.part', path)
        self.rows = []
        self.n_files += 1
