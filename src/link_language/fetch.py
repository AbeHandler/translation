"""Fetching a linked page's visible text: at most MAX_BYTES of it, decoded by the declared charset or, failing
that, by detection (charset_normalizer), since many Chinese sites serve GBK/GB2312."""
from dataclasses import dataclass

import charset_normalizer
import lxml.html

HEADERS = {'User-Agent': 'Mozilla/5.0 (research crawler; abha4861@colorado.edu)'}
MAX_BYTES = 2_000_000
TIMEOUT = 20


@dataclass
class Page:
    status: int
    final_url: str
    content_type: str
    title: str
    text: str


def decode(body, declared):
    if declared:
        try:
            return body.decode(declared)
        except (LookupError, UnicodeDecodeError):
            pass
    best = charset_normalizer.from_bytes(body).best()
    return str(best) if best else body.decode('utf-8', errors='replace')


def visible_text(html):
    """(title, text) of an HTML page, without scripts and styles."""
    doc = lxml.html.fromstring(html)
    for node in doc.xpath('//script|//style|//noscript'):
        node.drop_tree()
    title = doc.findtext('.//title') or ''
    body = doc.find('body')
    return ' '.join(title.split()), ' '.join((body if body is not None else doc).text_content().split())


def fetch_page(url, client):
    """Fetch url (following redirects) with an httpx.Client. Non-HTML pages (PDFs, images) get no text."""
    with client.stream('GET', url, headers=HEADERS, follow_redirects=True, timeout=TIMEOUT) as response:
        content_type = response.headers.get('content-type', '')
        body = b''
        if 'html' in content_type or 'text' in content_type or not content_type:
            for chunk in response.iter_bytes():
                body += chunk
                if len(body) >= MAX_BYTES:
                    break
        title, text = ('', '')
        if body.strip():
            title, text = visible_text(decode(body[:MAX_BYTES], response.charset_encoding))
        return Page(response.status_code, str(response.url), content_type, title, text)
