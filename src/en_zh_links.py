"""
Cleaning the collected English -> Chinese links (scripts/collect_queue.py output) of two known kinds of noise:
    failed fetches  the link was fetched but answered with an error status (404, 403, ...): the Chinese page
                    labelled is an error page ("找不到頁面"), not the page the article cites
    Chinese sources the source article was labelled English (news-please trusts <html lang="en">) but its title
                    is Chinese (chinaz.com, ithome.com, etnet.com.hk): its links are Chinese -> Chinese
and of one kind of double counting:
    syndication     one story copied to many sites (an NPR story on 34 member stations, wire stories) is one
                    citation, not many. story_ids groups the source articles into stories: articles citing the
                    same Chinese URL with the same normalised title or the same URL slug are copies of one story.
                    Only articles sharing a link are compared, so different stories on the same event, or
                    generic titles ("Morning briefing"), aren't merged.
and flags press releases (is_press_release): mostly written by the Chinese company itself, so they cite its own
pages rather than restate someone else's; most syndication is press releases on local TV sites (/prnewswire/).
and of sources not about AI: the queue kept articles saying "AI" anywhere on the page (menus, sidebars, "related
stories"); body_ai_mentions counts it in the article body only, so a TSMC story with an AI ticker can be dropped.
Source info (title, links file, body_ai_mentions) comes from the CC-NEWS links files (src/cc_news.py
ArticleLinkExtractor rows); for links files older than body_ai_mentions it is counted from the article's HTML
(cc_html/<warc>.parquet, reading only the row groups holding the wanted articles).
"""
import hashlib
import json
import logging
import os
import re
from collections import defaultdict
from urllib.parse import urlparse

import pyarrow.parquet as pq

from src.ai_mentions import mentions_ai_body
from src.link_language.script import ZH_MIN, han_share

logger = logging.getLogger(__name__)
URL_PREFIX = '{"url": "'  # every links-file line starts with the article's url (ArticleLinkExtractor.row)
PROGRESS_EVERY = 1000  # files


def fetch_failed(row):
    """True for a link labelled from a fetch that answered with an error status (host-cache labels have none)."""
    return row.get('label_source') == 'fetched' and row.get('status') not in (None, 200)


def chinese_title(title):
    return han_share(title or '') >= ZH_MIN


def line_url(line):
    """The article url at the start of a links-file line, without parsing the (long) rest of it."""
    if not line.startswith(URL_PREFIX):
        return json.loads(line)['url']
    end = line.index('"', len(URL_PREFIX))
    url = line[len(URL_PREFIX):end]
    return json.loads(line)['url'] if '\\' in url else url


def source_info(links_paths, urls):
    """{url: {title, links_file, body_ai_mentions}} for the articles in urls, read from the links files (only
    matching lines are parsed). body_ai_mentions is None for links files made before it was recorded."""
    urls, info = set(urls), {}
    for n, path in enumerate(links_paths, 1):
        with open(path, encoding='utf-8') as f:
            for line in f:
                if line_url(line) in urls:
                    row = json.loads(line)
                    info[row['url']] = {'title': row.get('title', ''), 'links_file': os.path.basename(path),
                                        'body_ai_mentions': row.get('body_ai_mentions')}
        if n % PROGRESS_EVERY == 0 or n == len(links_paths):
            logger.info('%d/%d links files read, %d of %d sources found', n, len(links_paths), len(info), len(urls))
    return info


def body_ai_mentions(html_path, urls):
    """{url: times "AI" is in the article body} for the articles in urls in one cc_html Parquet file, reading
    the HTML of only the row groups that hold one of them."""
    parquet, urls, counts = pq.ParquetFile(html_path), set(urls), {}
    for group in range(parquet.num_row_groups):
        if not urls.intersection(parquet.read_row_group(group, columns=['url']).column('url').to_pylist()):
            continue
        for row in parquet.read_row_group(group, columns=['url', 'html']).to_pylist():
            if row['url'] in urls:
                counts[row['url']] = mentions_ai_body(row['html'])
    return counts


TITLE_SEPARATORS = re.compile(r'\s+[|\-–—:]\s+')  # "Title - WSKG", "WVPE | Title"
MIN_SLUG_CHARS = 20  # shorter last path segments are ids (1748403.html, c.html), not headline slugs


def title_key(title):
    """A title's longest part between separators (drops a site name before or after it), lowercased, letters and
    digits only; '' when there's no title."""
    part = max(TITLE_SEPARATORS.split(title or ''), key=len)
    return ' '.join(re.sub(r'[^\w]+', ' ', part.lower()).split())


def slug_key(url):
    """The url's last path segment when it looks like a headline slug (trump-and-xi-meet-at-...), else ''."""
    segments = [seg for seg in urlparse(url).path.lower().split('/') if seg]
    slug = re.sub(r'\.s?html?$', '', segments[-1]) if segments else ''
    return slug if len(slug) >= MIN_SLUG_CHARS and '-' in slug else ''


def story_ids(rows, titles):
    """{srcpage: story_id}: source articles that cite the same Chinese URL with the same title key or slug key
    are one story (union-find; a story can span several of its links). story_id is a hash of the story's first
    article url, so it doesn't change between runs."""
    parent = {}

    def root(page):
        parent.setdefault(page, page)
        while parent[page] != page:
            parent[page] = parent[parent[page]]
            page = parent[page]
        return page

    by_target = defaultdict(set)
    for row in rows:
        root(row['srcpage'])
        by_target[row['url']].add(row['srcpage'])
    for pages in by_target.values():
        first = {}  # key -> first page with it
        for page in sorted(pages):
            for key in (('title', title_key(titles.get(page))), ('slug', slug_key(page))):
                if not key[1]:
                    continue
                if key in first:
                    a, b = root(first[key]), root(page)
                    parent[max(a, b)] = min(a, b)
                else:
                    first[key] = page
    return {page: hashlib.sha1(root(page).encode()).hexdigest()[:12] for page in parent}


PRESS_RELEASE_SITES = {  # registered domains of press-release wires
    'prnewswire.com', 'prnewswire.co.uk', 'newswire.ca', 'globenewswire.com', 'businesswire.com', 'accesswire.com',
    'einpresswire.com', 'acnnewswire.com', 'send2press.com', 'prweb.com', 'newsfilecorp.com', 'openpr.com',
    'issuewire.com', 'exclusivepress.net', 'express-press-release.net'}
PRESS_RELEASE_PATHS = {  # path segments of wire copies on other sites (wsaz.com/prnewswire/2023/...)
    'prnewswire', 'globenewswire', 'businesswire', 'accesswire', 'news-releases', 'news-release', 'press-releases',
    'press-release', 'aapreleases'}


def is_press_release(url):
    """True for a page on a press-release wire, or a wire copy (by its path) on another site."""
    host = (urlparse(url).hostname or '').removeprefix('www.')
    segments = set(urlparse(url).path.lower().split('/'))
    return any(host == site or host.endswith('.' + site) for site in PRESS_RELEASE_SITES) or bool(
        segments & PRESS_RELEASE_PATHS)
