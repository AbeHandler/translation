"""
The external links in an article's wikitext (which articles are about AI: src/ai_mentions.py).

external_links finds the URLs in cite templates (url=, archive-url=) and bracketed links. Archive copies
(web.archive.org, archive.today) and Wikimedia's own sites are dropped: the original URL is in the same
citation, and the aim is the sources outside Wikipedia.
"""
import re

URL = re.compile(r'https?://[^\s|\]\}<>"\'{]+')
SKIP_HOSTS = re.compile(r'^https?://([a-z0-9-]+\.)*(archive\.org|archive\.today|archive\.ph|archive\.is|'
                        r'wikipedia\.org|wikimedia\.org|wikidata\.org|wiktionary\.org|wikisource\.org)(/|$|:)', re.I)
TRAILING = '.,;:!?)'


def external_links(wikitext):
    """Unique external URLs in the wikitext, in order of first appearance."""
    seen = []
    for match in URL.finditer(wikitext):
        url = match.group(0).rstrip(TRAILING)
        if SKIP_HOSTS.match(url) or url in seen:
            continue
        seen.append(url)
    return seen
