"""Publication date of a web page, from its HTML. Tries, most to least trustworthy:

1. newspaper    newspaper4k's date extractor: URL, JSON-LD and meta tags. Full timestamp when the page has
                one (e.g. chinadaily: 2026-09-11T15:52:23+08:00). Only this extractor runs, not the full
                article parse, so it is cheap.
2. htmldate     htmldate without extensive search: metadata plus common bylines like
                <span class="time">2026/09/16</span> (zhidx). Day only.
3. htmldate_extensive  htmldate scanning the whole page for anything date-like. Finds bylines the others miss
                (leiphone's <td class="time">), but on section pages and homepages it guesses from copyright
                years and listed articles (e.g. 2026-01-01), so treat it as a guess.
"""
from htmldate import find_date
from newspaper.configuration import Configuration
from newspaper.extractors.pubdate_extractor import PubdateExtractor
from newspaper.parsers import fromstring

NEWSPAPER_PUBDATE = PubdateExtractor(Configuration())


def extract_pubdate(html, url):
    """(ISO date string, source), where source says which step above found it, or (None, None)."""
    doc = fromstring(html)
    found = NEWSPAPER_PUBDATE.parse(url, doc) if doc is not None else None
    if found:
        return found.isoformat(), 'newspaper'
    found = find_date(html, url=url, original_date=True, extensive_search=False)
    if found:
        return found, 'htmldate'
    found = find_date(html, url=url, original_date=True, extensive_search=True)
    if found:
        return found, 'htmldate_extensive'
    return None, None
