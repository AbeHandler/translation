"""
Seed documents: the primary sources behind media storms, as opposed to news coverage of them. A storm's cited
documents (src/media_storms.py storm_seeds) mix both: the Anthropic statement, the Truth Social post, the court
filing, but also Bloomberg's scoop or AP's related stories. A document is a primary source when its site is not a
news outlet (not one of the corpus's own outlets, nor a major outlet outside it), and it is a single document:
a post rather than a profile, not a shop or an affiliate link. Files a news outlet hosts as sources (a PDF, a
/documents/ page, DocumentCloud) are primary sources too: the Washington Post's copy of a memo is the memo.
Logic only.
"""
import re

from src.external_links import registered_domain

# major outlets that are cited but missing from (or rare in) CC-NEWS
NEWS_DOMAINS = {'bloomberg.com', 'nytimes.com', 'wsj.com', 'ft.com', 'reuters.com', 'apnews.com', 'ap.org',
                'cnbc.com', 'cnn.com', 'bbc.co.uk', 'bbc.com', 'washingtonpost.com', 'theguardian.com',
                'theverge.com', 'techcrunch.com', 'axios.com', 'politico.com', 'theinformation.com', 'wired.com',
                'npr.org', 'hollywoodreporter.com', 'variety.com', 'deadline.com', 'businessinsider.com',
                'semafor.com', 'afp.com', 'nbcnews.com', 'cbsnews.com', 'abcnews.go.com', 'foxnews.com',
                'foxbusiness.com', 'scrippsnews.com', 'newscientist.com', 'translate.goog', 'books.google.com',
                'urldefense.com', 'bestreviews.com', 'amazon.com', 'trx-hub.com', 'fave.co'}
HOSTED_DOCUMENT = re.compile(r'\.pdf$|/documents?/|^(\w+\.)?documentcloud\.org/|^assets\.|^s3\.|^static\.', re.I)
SOCIAL = ('x.com', 'truthsocial.com', 'threads.net', 'facebook.com', 'instagram.com', 'linkedin.com',
          'youtube.com', 'bsky.app', 'weibo.com')
POST = re.compile(r'/(status|posts|post|p|watch|reel|videos)/|/feed/update/')
KINDS = [  # (kind, document key pattern), first match wins
    ('social post', re.compile(r'^(x\.com|truthsocial\.com|threads\.net|facebook\.com|instagram\.com|linkedin\.com|'
                               r'youtube\.com|bsky\.app|weibo\.com)/')),
    ('court or legal', re.compile(r'courtlistener|uscourts|supremecourt|/court|law\.')),
    ('government', re.compile(r'(\.gov|\.gov\.\w\w|\.mil|europa\.eu|\.int|parliament|\.gouv\.)(/|$)')),
    ('research', re.compile(r'arxiv\.org|nature\.com|science\.org|thelancet|nih\.gov|ssrn|acm\.org|ieee|metr\.org|'
                            r'openreview|biorxiv|medrxiv|\.edu/')),
]


def source_kind(document, news_domains=()):
    """'social post', 'court or legal', 'government', 'research', 'hosted document' (a file a news outlet or
    DocumentCloud hosts) or 'organisation' (a company or group's own site: blog, newsroom, statement)."""
    domain = registered_domain('https://' + document.split('/')[0])
    for kind, pattern in KINDS:
        if pattern.search(document):
            return kind
    if domain in news_domains or domain in NEWS_DOMAINS or domain == 'documentcloud.org':
        return 'hosted document'
    return 'organisation'


def is_primary(document, news_domains):
    """True for a primary source: not on a news outlet (news_domains: the corpus's outlets, plus NEWS_DOMAINS)
    and a single document (a social media post, not a profile)."""
    host = document.split('/')[0]
    domain = registered_domain('https://' + host)
    if domain in news_domains or domain in NEWS_DOMAINS or host in NEWS_DOMAINS:
        return bool(HOSTED_DOCUMENT.search(document)) and 'amazon.com' not in host
    if domain in SOCIAL or host in SOCIAL:
        return bool(POST.search('/' + document.split('/', 1)[1] + '/')) if '/' in document else False
    return True
