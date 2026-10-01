"""
Cleaning the collected English -> Chinese links (scripts/collect_queue.py output) of two known kinds of noise:
    failed fetches  the link was fetched but answered with an error status (404, 403, ...): the Chinese page
                    labelled is an error page ("找不到頁面"), not the page the article cites
    Chinese sources the source article was labelled English (news-please trusts <html lang="en">) but its title
                    is Chinese (chinaz.com, ithome.com, etnet.com.hk): its links are Chinese -> Chinese
Source titles come from the CC-NEWS links files (src/cc_news.py ArticleLinkExtractor rows: {url, title, ...}).
"""
import json
import logging

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
