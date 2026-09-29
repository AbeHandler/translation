"""
Deciding which articles are about AI, and finding the external links in their wikitext.

mentions_ai counts "AI" as a word of its own: not inside other Latin words ("MAIL", "Aida"), but it may touch
Chinese characters ("AI芯片"), so plain \\b word boundaries (which treat CJK as word characters) aren't used.

external_links finds the URLs in cite templates (url=, archive-url=) and bracketed links. Archive copies
(web.archive.org, archive.today) and Wikimedia's own sites are dropped: the original URL is in the same
citation, and the aim is the sources outside Wikipedia.
"""
import re

AI = re.compile(r'(?<![A-Za-z])AI(?![A-Za-z])')
URL = re.compile(r'https?://[^\s|\]\}<>"\'{]+')
SKIP_HOSTS = re.compile(r'^https?://([a-z0-9-]+\.)*(archive\.org|archive\.today|archive\.ph|archive\.is|'
                        r'wikipedia\.org|wikimedia\.org|wikidata\.org|wiktionary\.org|wikisource\.org)(/|$|:)', re.I)
TRAILING = '.,;:!?)'


def mentions_ai(text):
    return len(AI.findall(text))


def external_links(wikitext):
    """Unique external URLs in the wikitext, in order of first appearance."""
    seen = []
    for match in URL.finditer(wikitext):
        url = match.group(0).rstrip(TRAILING)
        if SKIP_HOSTS.match(url) or url in seen:
            continue
        seen.append(url)
    return seen
