"""
The store of primary sources' raw text: a to-do list (<dir>/todo.tsv: one URL per line; scripts/add_primary_todo.py
adds to it from any list of URLs, or append to it yourself), and one JSON file per URL fetched,
<dir>/<sha1 of the URL's key>.json {key, url, final_url, status, content_type, title, text, n_chars, fetched_at}
(scripts/fetch_primary_sources.py works through the list). The key is the URL normalized (source_key), so
twitter.com and x.com, or links with and without ?utm=, share one file. Each kind of source has its way in:
    X/Twitter posts   the public oEmbed endpoint (publish.twitter.com): the post's text, no login
    Truth Social      its public status API (truthsocial.com/api/v1/statuses/<id>)
    PDFs              the file's text (pypdf), at most MAX_PDF_PAGES pages
    anything else     the page's main text (readability), or all its visible text when readability keeps little
Only text is kept (at most MAX_TEXT_CHARS), not the HTML or file. Logic only.
"""
import datetime
import hashlib
import io
import json
import os
import re

import httpx
import lxml.html

from src.link_language.fetch import HEADERS, decode

MAX_TEXT_CHARS = 200_000
MAX_BYTES = 30_000_000
MAX_PDF_PAGES = 200
MIN_MAIN_CHARS = 200          # readability keeping less than this: use the whole page's text
TIMEOUT = 30
X_POST = re.compile(r'^https?://(?:www\.|mobile\.)?(?:twitter|x)\.com/\w+/status/(\d+)', re.I)
TRUTH_POST = re.compile(r'^https?://(?:www\.)?truthsocial\.com/@\w+/(?:posts/)?(\d+)', re.I)


def html_text(html):
    """(title, text): readability's title and main text, or all the visible text if that keeps little."""
    from readability import Document
    try:
        doc = Document(html)
        title = doc.short_title()
        main = lxml.html.fromstring(doc.summary()).text_content()
    except Exception:
        title, main = '', ''
    main = '\n'.join(line.strip() for line in main.splitlines() if line.strip())
    if len(main) < MIN_MAIN_CHARS:
        try:
            tree = lxml.html.fromstring(html)
            for bad in tree.xpath('//script|//style|//noscript'):
                bad.drop_tree()
            main = '\n'.join(line.strip() for line in tree.text_content().splitlines() if line.strip())
            title = title or (tree.findtext('.//title') or '').strip()
        except Exception:
            pass
    return title, main


def pdf_text(data):
    from pypdf import PdfReader
    reader = PdfReader(io.BytesIO(data))
    pages = [page.extract_text() or '' for page in reader.pages[:MAX_PDF_PAGES]]
    title = (reader.metadata.title if reader.metadata and reader.metadata.title else '') or ''
    return str(title), '\n'.join(pages)


def source_key(url):
    """The URL normalized (src/media_storms.py document_key: no www., query or fragment; twitter.com is x.com), so
    variants of one URL share a file; the URL itself when it has no document key (a homepage)."""
    from src.media_storms import document_key
    return document_key(url) or url.strip()


def source_path(texts_dir, url):
    """<texts_dir>/<sha1 of the URL's key>.json"""
    return os.path.join(texts_dir, hashlib.sha1(source_key(url).encode('utf-8')).hexdigest() + '.json')


BARE_URL = re.compile(r'^[\w-]+(\.[\w-]+)+(/\S*)?$')   # anthropic.com/news/x: a URL without its scheme


def as_url(text):
    """text as a URL: as is with http(s)://, https:// added to a bare address (anthropic.com/news/x), else None."""
    text = text.strip()
    if text.startswith(('http://', 'https://')):
        return text
    return 'https://' + text if BARE_URL.match(text) else None


def read_todo(path):
    """{source key: url} of the to-do list: one URL per line, with or without https:// (anything after a tab is
    ignored, and lines that aren't URLs, like a header, are skipped); the first URL per key."""
    if not os.path.exists(path):
        return {}
    todo = {}
    with open(path, encoding='utf-8') as f:
        for line in f:
            url = as_url(line.split('\t')[0])
            if url:
                todo.setdefault(source_key(url), url)
    return todo


class SourceFetcher:
    def __init__(self, client=None):
        self.client = client or httpx.Client(headers=HEADERS, follow_redirects=True, timeout=TIMEOUT)

    def x_post(self, href):
        r = self.client.get('https://publish.twitter.com/oembed', params={'url': href, 'omit_script': 'true'})
        if r.status_code != 200:
            return {'status': r.status_code, 'final_url': href, 'content_type': 'oembed', 'title': '', 'text': ''}
        data = r.json()
        text = lxml.html.fromstring(data.get('html') or '<p></p>').text_content().strip()
        return {'status': 200, 'final_url': data.get('url', href), 'content_type': 'oembed',
                'title': data.get('author_name', ''), 'text': text}

    def truth_post(self, post_id, href):
        r = self.client.get(f'https://truthsocial.com/api/v1/statuses/{post_id}')
        if r.status_code != 200:
            return {'status': r.status_code, 'final_url': href, 'content_type': 'truth api', 'title': '', 'text': ''}
        data = r.json()
        text = lxml.html.fromstring(data.get('content') or '<p></p>').text_content().strip()
        return {'status': 200, 'final_url': data.get('url', href), 'content_type': 'truth api',
                'title': (data.get('account') or {}).get('display_name', ''), 'text': text}

    def page(self, href):
        with self.client.stream('GET', href) as r:
            body = b''
            for chunk in r.iter_bytes():
                body += chunk
                if len(body) >= MAX_BYTES:
                    break
            content_type = r.headers.get('content-type', '')
            final_url, status, charset = str(r.url), r.status_code, r.charset_encoding
        if status != 200 or not body:
            title, text = '', ''
        elif 'pdf' in content_type or body[:5] == b'%PDF-':
            title, text = pdf_text(body)
        else:
            title, text = html_text(decode(body, charset))
        return {'status': status, 'final_url': final_url, 'content_type': content_type, 'title': title, 'text': text}

    def text(self, href):
        """{status, final_url, content_type, title, text, n_chars, fetched_at} of href. A failed fetch raises."""
        match = X_POST.match(href)
        if match:
            out = self.x_post(f'https://twitter.com/i/status/{match.group(1)}')
        elif TRUTH_POST.match(href):
            out = self.truth_post(TRUTH_POST.match(href).group(1), href)
        else:
            out = self.page(href)
        out['text'] = (out['text'] or '')[:MAX_TEXT_CHARS]
        return {**out, 'n_chars': len(out['text']),
                'fetched_at': datetime.datetime.now(datetime.timezone.utc).isoformat(timespec='seconds')}


STORE_SCHEMA = [('key', 'string'), ('url', 'string'), ('final_url', 'string'), ('status', 'int32'),
                ('content_type', 'string'), ('title', 'string'), ('text', 'string'), ('n_chars', 'int32'),
                ('fetched_at', 'string'), ('error', 'string')]


def compile_store(store_dir, out_path):
    """Every <store_dir>/*.json as one Parquet table at out_path, a row per source, sorted by URL; written under a
    name of this process's own and then renamed, so workers compiling at once never clobber each other. Returns
    the rows."""
    import glob
    import pyarrow as pa
    import pyarrow.parquet as pq
    schema = pa.schema([(name, getattr(pa, kind)()) for name, kind in STORE_SCHEMA])
    rows = []
    for path in glob.glob(os.path.join(store_dir, '*.json')):
        with open(path, encoding='utf-8') as f:
            source = json.load(f)
        rows.append({name: source.get(name) for name in schema.names})
    rows.sort(key=lambda r: r['url'] or '')
    part = f'{out_path}.{os.getpid()}.part'
    pq.write_table(pa.Table.from_pylist(rows, schema), part, compression='zstd')
    os.replace(part, out_path)
    return rows
