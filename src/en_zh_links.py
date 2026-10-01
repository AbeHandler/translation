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
Source titles come from the CC-NEWS links files (src/cc_news.py ArticleLinkExtractor rows: {url, title, ...}).
"""
import hashlib
import json
import logging
import re
from collections import defaultdict
from urllib.parse import urlparse

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


def source_titles(links_paths, urls):
    """{url: title} for the articles in urls, read from the links files (only matching lines are parsed)."""
    urls, titles = set(urls), {}
    for n, path in enumerate(links_paths, 1):
        with open(path, encoding='utf-8') as f:
            for line in f:
                if line_url(line) in urls:
                    titles[line_url(line)] = json.loads(line).get('title', '')
        if n % PROGRESS_EVERY == 0 or n == len(links_paths):
            logger.info('%d/%d links files read, %d of %d source titles found', n, len(links_paths), len(titles),
                        len(urls))
    return titles


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
