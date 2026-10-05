"""
Primary sources found from the links themselves, not from storms: every document that AI news articles link to,
counted by the outlets linking to it, kept if it is a primary source (src/seed_documents.py: not news coverage),
ranked by how many outlets linked to it within SPREAD_DAYS of its first link (a source that set off coverage is
linked by many outlets at once). Both corpora: English CC-NEWS articles and the Chinese site crawls. Logic only.

    links    one corpus file's articles -> rows {document, href, article, outlet, date, language}
    sources  all rows -> one row per primary source: {document, href, kind, first_seen, outlets_first, outlets,
             articles, en_outlets, zh_outlets, example}
"""
import datetime
from collections import defaultdict

import pyarrow as pa

from src.external_links import external_links, registered_domain
from src.media_storms import document_key
from src.seed_documents import NEWS_DOMAINS, is_primary, source_kind

SPREAD_DAYS = 14           # outlets_first: outlets linking within this many days of the first link
MIN_OUTLETS = 3            # a source is linked by at least this many outlets
LINK_SCHEMA = pa.schema([('document', pa.string()), ('href', pa.string()), ('article', pa.string()),
                         ('outlet', pa.string()), ('date', pa.string()), ('language', pa.string())])


def link_rows(article_url, hrefs, date, language):
    """One row per document the article links to outside its own site."""
    outlet = registered_domain(article_url)
    seen = set()
    for href in external_links(article_url, hrefs):
        key = document_key(href)
        if key and key not in seen:
            seen.add(key)
            yield {'document': key, 'href': href, 'article': article_url, 'outlet': outlet, 'date': date,
                   'language': language}


def primary_sources(rows, outlets=None, spread_days=SPREAD_DAYS, min_outlets=MIN_OUTLETS):
    """rows: link rows (dicts) from every corpus; outlets: every outlet in the corpora (news, so not primary
    sources; default: the rows' outlets). Returns one summary per primary source, most outlets within spread_days
    of its first link first."""
    news = (set(outlets) if outlets is not None else {r['outlet'] for r in rows}) | NEWS_DOMAINS
    by_doc = defaultdict(list)
    for r in rows:
        if r['date']:
            by_doc[r['document']].append(r)
    found = []
    for doc, links in by_doc.items():
        if len({r['outlet'] for r in links}) < min_outlets or not is_primary(doc, news):
            continue
        first = min(r['date'] for r in links)
        cutoff = (datetime.date.fromisoformat(first) + datetime.timedelta(days=spread_days)).isoformat()
        early = {r['outlet'] for r in links if r['date'] <= cutoff}
        found.append({'document': doc, 'href': links[0]['href'], 'kind': source_kind(doc, news), 'first_seen': first,
                      'outlets_first': len(early), 'outlets': len({r['outlet'] for r in links}),
                      'articles': len({r['article'] for r in links}),
                      'en_outlets': len({r['outlet'] for r in links if r['language'] == 'en'}),
                      'zh_outlets': len({r['outlet'] for r in links if r['language'] == 'zh'}),
                      'example': min(links, key=lambda r: r['date'])['article']})
    return sorted(found, key=lambda s: (-s['outlets_first'], -s['outlets']))
