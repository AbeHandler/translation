"""
The Chinese pages English articles link to, fetched once each as documents: a shard-queue row processor
({url} -> the page's main text, title and publication date), for scripts/process_queue.py -processor zh_doc.
The raw HTML is kept (<html_dir>/<sha1 of url>.html.gz), so the text can be re-extracted later, and the Chinese
side of a restatement doesn't change when the page does.

The title is the document's own (og:title, <h1>), not the page's <title>, and the date prefers one in the URL
(see doc_date).

A page counts as a document (is_document) when it answered 200, isn't a site's homepage, its title doesn't say
it's an error page (many answer 200: "系统维护", "账号已迁移"), and its main text has at least MIN_DOC_HAN Chinese
characters: a blog post, statement, speech or article, not a homepage, store, video page or error page.
Restatement is then checked only against documents.
"""
import gzip
import hashlib
import os
import re
from urllib.parse import urlparse

import httpx
import lxml.html

from src.extract_pubdate import extract_pubdate
from src.link_language.fetch import fetch_html
from src.restatement.pages import han_count, main_text

MIN_DOC_HAN = 100  # a short statement or post still counts; menus and error pages have less
ERROR_TITLE = re.compile(r'系统维护|维护中|页面不存在|找不到|不存在|已删除|已迁移|出错|错误|404|not found|error',
                         re.IGNORECASE)
MAX_TEXT_CHARS = 100_000  # in the result row; the HTML file has everything
HOMEPAGE_PATHS = {'', '/', '/index.html', '/index.htm', '/index.shtml', '/index.php', '/default.aspx'}


def is_homepage(url):
    parsed = urlparse(url)
    return parsed.path.lower() in HOMEPAGE_PATHS and not parsed.query


TITLE_SEPARATORS = re.compile(r'\s*[|_｜]\s*|\s+[-–—]\s+')
MIN_TITLE_CHARS = 4


def page_title(html):
    """The document's own title: og:title, else the first <h1>, else <title> up to its first separator (most
    put the site name after it: "生成式人工智能服务管理暂行办法_中央网络安全和信息化委员会办公室"). WeChat
    articles have an empty <title>; many government pages have only the section and site name there."""
    try:
        doc = lxml.html.fromstring(html)
    except Exception:
        return ''
    candidates = doc.xpath('//meta[@property="og:title"]/@content') + [h1.text_content() for h1 in doc.iter('h1')]
    for candidate in candidates:
        candidate = ' '.join(candidate.split())
        if len(candidate) >= MIN_TITLE_CHARS:
            return candidate
    title = ' '.join((doc.findtext('.//title') or '').split())
    first = TITLE_SEPARATORS.split(title)[0]
    return first if len(first) >= MIN_TITLE_CHARS else title


URL_DATE = re.compile(r'(?<!\d)(20\d\d)[-/_]?(0[1-9]|1[0-2])[-/_]?(0[1-9]|[12]\d|3[01])(?!\d)')
URL_YEAR = re.compile(r'/(20\d\d)/')
WECHAT_DATE = re.compile(r"create_time:\s*'(\d{4}-\d\d-\d\d)")


def doc_date(html, url, extracted):
    """(ISO date, source) of a document: a full date in its URL (cac.gov.cn/2023-07/13/..., t20230221_...) or
    a WeChat article's create_time beat the date extractor (which can pick a page's update or fetch date); an
    extracted date in another year than the URL's (/art/2023/...) is dropped as wrong."""
    match = URL_DATE.search(url)
    if match:
        return '-'.join(match.groups()), 'url'
    match = WECHAT_DATE.search(html) if 'mp.weixin.qq.com' in url else None
    if match:
        return match.group(1), 'wechat'
    year = URL_YEAR.search(urlparse(url).path)
    if extracted and year and not extracted.startswith(year.group(1)):
        return None, None
    return (extracted[:10], 'html') if extracted else (None, None)


class ZhDocFetcher:
    def __init__(self, html_dir, fetch=fetch_html):
        self.html_dir = html_dir
        self.fetch = fetch  # (url, client) -> RawPage
        self.client = httpx.Client()
        os.makedirs(html_dir, exist_ok=True)

    def html_path(self, url):
        return os.path.join(self.html_dir, hashlib.sha1(url.encode()).hexdigest() + '.html.gz')

    def save_html(self, url, html):
        path = self.html_path(url)
        with gzip.open(path + '.part', 'wt', encoding='utf-8') as f:
            f.write(html)
        os.rename(path + '.part', path)

    def doc(self, row):
        """{status, final_url, content_type, title, pubdate, pubdate_source, n_han, is_homepage, is_document,
        text}. A fetch that fails raises, and the queue records the error."""
        page = self.fetch(row['url'], self.client)
        text, title, pubdate, pubdate_source = '', '', None, None
        if page.html:
            self.save_html(row['url'], page.html)
            text, title = main_text(page.html), page_title(page.html)
            pubdate, pubdate_source = doc_date(page.html, row['url'], extract_pubdate(page.html, page.final_url)[0])
        n_han = han_count(text)
        homepage = is_homepage(row['url']) or is_homepage(page.final_url)
        is_document = (page.status == 200 and not homepage and not ERROR_TITLE.search(title)
                       and n_han >= MIN_DOC_HAN)
        return {'status': page.status, 'final_url': page.final_url, 'content_type': page.content_type,
                'title': title[:300], 'pubdate': pubdate, 'pubdate_source': pubdate_source, 'n_han': n_han,
                'is_homepage': homepage, 'is_document': is_document, 'text': text[:MAX_TEXT_CHARS]}
