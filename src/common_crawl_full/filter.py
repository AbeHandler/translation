"""
One WARC -> its English pages that say "AI", as a gzipped WARC of their response records (headers and body as
crawled). Cheap checks first: an HTML response whose raw bytes contain "AI" at all; then "AI" as a word in the
page's visible text (src/ai_mentions.py); then English (langdetect on the visible text; recent crawls carry no
language tag).
"""
import io
import logging
import os
import time
import urllib.request

from langdetect import DetectorFactory, LangDetectException, detect
from warcio.archiveiterator import ArchiveIterator
from warcio.warcwriter import WARCWriter

from src.ai_mentions import mentions_ai_html
from src.common_crawl_full.index import DATA_URL, TIMEOUT

DetectorFactory.seed = 0
logger = logging.getLogger(__name__)
KEEP_HEADERS = ('WARC-Target-URI', 'WARC-Date', 'WARC-Record-ID', 'WARC-Payload-Digest', 'WARC-IP-Address',
                'WARC-Identified-Payload-Type', 'WARC-Identified-Content-Language')
LOG_EVERY = 10000  # records


def is_english_ai_page(body):
    """(keep, n_ai): "AI" as a word in the visible text, and the text is English."""
    n_ai, text = mentions_ai_html(body)
    if not n_ai:
        return False, 0
    try:
        return detect(text[:3000]) == 'en', n_ai
    except LangDetectException:
        return False, n_ai


def filter_warc(path, out_path, opener=urllib.request.urlopen):
    """Stream DATA_URL + path and write its English AI pages to out_path (via .part). Returns counts."""
    counts = {'responses': 0, 'html': 0, 'kept': 0}
    started = time.time()
    with opener(DATA_URL + path, timeout=TIMEOUT) as stream, open(out_path + '.part', 'wb') as out:
        writer = WARCWriter(out, gzip=True)
        for record in ArchiveIterator(stream):
            if record.rec_type != 'response':
                continue
            counts['responses'] += 1
            if counts['responses'] % LOG_EVERY == 0:
                logger.info('%s: %d responses, %d kept (%.0fs)', os.path.basename(path), counts['responses'],
                            counts['kept'], time.time() - started)
            content_type = (record.http_headers.get_header('Content-Type') or '') if record.http_headers else ''
            if 'html' not in content_type:
                continue
            counts['html'] += 1
            body = record.content_stream().read()
            keep, n_ai = is_english_ai_page(body)
            if not keep:
                continue
            headers = {name: record.rec_headers.get_header(name) for name in KEEP_HEADERS
                       if record.rec_headers.get_header(name)}
            headers['X-AI-Mentions'] = str(n_ai)
            writer.write_record(writer.create_warc_record(
                headers['WARC-Target-URI'], 'response', payload=io.BytesIO(body), length=len(body),
                warc_headers_dict=headers, http_headers=record.http_headers))
            counts['kept'] += 1
    os.rename(out_path + '.part', out_path)
    counts['seconds'] = round(time.time() - started)
    return counts
