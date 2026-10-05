"""
Which primary source is a piece of text taken from? For a screenshot's OCR text, the source in the store
(data/processed/primary.pq) it shares the most five-word phrases with. Phrases are lowercased words and numbers,
punctuation dropped, so OCR noise in some words still leaves intact phrases to match. Phrases found in more than
MAX_SOURCES_PER_PHRASE sources are stock wording or site menus ("we are excited to announce", a site's navigation)
and don't count, and listing pages (/news, /blog) aren't sources. Logic only.
"""
import re
from collections import Counter, defaultdict
from urllib.parse import urlparse

N = 5                       # words per phrase
MAX_SOURCES_PER_PHRASE = 5  # a phrase in more sources than this says nothing about which one
MIN_SHARED = 5              # a match shares at least this many phrases (3-4 were mostly stock wording)
WORD = re.compile(r'[a-z0-9]+')
LISTING_PATHS = {'', 'news', 'blog', 'press', 'newsroom', 'research', 'updates', 'index', 'en', 'zh', 'stories'}


def phrases(text, n=N):
    words = WORD.findall((text or '').lower())
    return {' '.join(words[i:i + n]) for i in range(len(words) - n + 1)}


def is_listing(url):
    """A site's front or listing page (anthropic.com/news): every headline is on it, so it 'matches' anything."""
    path = urlparse(url).path.strip('/').lower()
    return path in LISTING_PATHS or path.split('/')[-1] in LISTING_PATHS and path.count('/') < 1


class SourceIndex:
    def __init__(self, sources, max_sources_per_phrase=MAX_SOURCES_PER_PHRASE):
        """sources: [{url, title, text}]."""
        index = defaultdict(set)
        self.titles = {}
        for s in sources:
            if is_listing(s['url']):
                continue
            self.titles[s['url']] = s['title']
            for p in phrases(f"{s['title']} {s['text']}"):
                index[p].add(s['url'])
        self.index = {p: urls for p, urls in index.items() if len(urls) <= max_sources_per_phrase}

    def match(self, text, min_shared=MIN_SHARED):
        """[(url, shared phrases)] of the sources sharing at least min_shared phrases with text, most first."""
        shared = Counter(url for p in phrases(text) for url in self.index.get(p, ()))
        return [(url, n) for url, n in shared.most_common() if n >= min_shared]
