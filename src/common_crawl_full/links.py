"""
The links of the English AI pages kept from the regular Common Crawl (filter.py), for the link queue:
    page_links   <warc>.ai.warc.gz -> <warc>.links.jsonl: each page's body links (readability, as for CC-NEWS:
                 src/cc_news.py ArticleLinkExtractor), one line per page {url, record_id, n_links, links}
    queue_rows   links files -> {srcpage, url} for every external link (src/external_links.py)
"""
import glob
import json
import os

from warcio.archiveiterator import ArchiveIterator

from src.cc_news import ArticleLinkExtractor, write_jsonl
from src.external_links import external_links


def page_links(ai_warc_path, out_path):
    """Write out_path (atomically). Returns counts."""
    extractor = ArticleLinkExtractor()
    rows, n_pages = [], 0
    with open(ai_warc_path, 'rb') as f:
        for record in ArchiveIterator(f):
            if record.rec_type != 'response':
                continue
            n_pages += 1
            row = extractor.row({'url': record.rec_headers.get_header('WARC-Target-URI'), 'language': 'en',
                                 'record_id': record.rec_headers.get_header('WARC-Record-ID'),
                                 'html': record.content_stream().read()})
            if row:
                rows.append(row)
    write_jsonl(out_path, rows)
    return {'pages': n_pages, 'parsed': len(rows), 'links': sum(r['n_links'] for r in rows)}


def links_path(ai_warc_path):
    return ai_warc_path.removesuffix('.ai.warc.gz') + '.links.jsonl'


def queue_rows(out_dir):
    """{srcpage, url} for every external link in every links file of out_dir."""
    for path in sorted(glob.glob(os.path.join(out_dir, '*.links.jsonl'))):
        with open(path, encoding='utf-8') as f:
            for line in f:
                page = json.loads(line)
                for href in external_links(page['url'], (link['href'] for link in page['links'])):
                    yield {'srcpage': page['url'], 'url': href}
