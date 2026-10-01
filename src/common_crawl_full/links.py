"""
The links of the English AI pages kept from the regular Common Crawl (filter.py), for the link queue:
    page_links   <warc>.ai.warc.gz -> <warc>.links.jsonl: each page's body links (readability, as for CC-NEWS:
                 src/cc_news.py ArticleLinkExtractor), one line per page {url, record_id, n_links, links}
    queue_shards each links file -> one shard of the cc_full queue, shard_<warc>.jsonl: {srcpage, url} for every
                 external link (src/external_links.py). One shard per WARC, written once, so the queue grows as
                 WARCs get links and never needs all links in memory (55k WARCs: ~100M links)
    delete_linked_warcs  the cleanup step: empties each AI WARC whose links file exists (the links are all that
                 is used downstream; the empty file keeps marking the WARC done)
"""
import glob
import json
import os
import re

from warcio.archiveiterator import ArchiveIterator

from src.cc_news import ArticleLinkExtractor, write_jsonl
from src.common_crawl_full.worker import links_path
from src.external_links import external_links
from src.file_worker import delete_done_inputs
from src.shard_queue.shards import results_dir


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


def queue_rows(links_path):
    """{srcpage, url} for every external link in one links file, each once."""
    rows = {}
    with open(links_path, encoding='utf-8') as f:
        for line in f:
            page = json.loads(line)
            for href in external_links(page['url'], (link['href'] for link in page['links'])):
                rows[(page['url'], href)] = {'srcpage': page['url'], 'url': href}
    return list(rows.values())


LEGACY_SHARD = re.compile(r'shard_[0-9a-f]{16}\.jsonl$')  # content-hash shards of the old, all-in-memory queue


def queue_shards(out_dir, queue_dir):
    """Write queue_dir/shard_<warc>.jsonl for every links file in out_dir that has no shard (or result) yet.
    First deletes old content-hash shards without results: their links are in the per-WARC shards. Returns
    (shards written, links in them)."""
    os.makedirs(queue_dir, exist_ok=True)
    for name in os.listdir(queue_dir):
        if LEGACY_SHARD.match(name) and not os.path.exists(os.path.join(results_dir(queue_dir), name)):
            os.remove(os.path.join(queue_dir, name))
    n_shards = n_rows = 0
    for path in sorted(glob.glob(os.path.join(out_dir, '*.links.jsonl'))):
        name = 'shard_' + os.path.basename(path).removesuffix('.links.jsonl') + '.jsonl'
        shard = os.path.join(queue_dir, name)
        if os.path.exists(shard) or os.path.exists(os.path.join(results_dir(queue_dir), name)):
            continue
        rows = queue_rows(path)
        write_jsonl(shard, rows)
        n_shards, n_rows = n_shards + 1, n_rows + len(rows)
    return n_shards, n_rows


def delete_linked_warcs(out_dir):
    """Empty every <name>.ai.warc.gz in out_dir that has its <name>.links.jsonl: the space is freed, and the empty
    file still tells every filter worker (also ones started before links files counted as done) that the WARC is
    done. Returns (emptied, bytes freed)."""
    paths = [os.path.join(out_dir, name) for name in os.listdir(out_dir) if name.endswith('.ai.warc.gz')]
    return delete_done_inputs(paths, links_path, keep_empty=True)
