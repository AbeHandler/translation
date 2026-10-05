"""
Primary sources found from the links themselves, not from storms: every document that AI news articles link to,
counted by the outlets linking to it, kept if it is a primary source (src/seed_documents.py: not news coverage),
ranked by how many outlets linked to it within SPREAD_DAYS of its first link (a source that set off coverage is
linked by many outlets at once). Two corpora, each its own run: English CC-NEWS articles, and the Chinese site
crawls (pages about AI by config/chinese_ai_terms.txt; their article-body links, as for English). Logic only.

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

# major Chinese outlets and portals outside our crawls: their articles are coverage, not sources
NEWS_DOMAINS_ZH = {'sina.com.cn', 'sina.cn', 'sohu.com', '163.com', 'ifeng.com', 'xinhuanet.com', 'news.cn',
                   'people.com.cn', 'people.cn', 'cctv.com', 'cctv.cn', 'chinanews.com', 'chinanews.com.cn',
                   'thepaper.cn', 'caixin.com', 'yicai.com', 'jiemian.com', '36kr.com', 'huxiu.com', 'ithome.com',
                   'chinadaily.com.cn', 'globaltimes.cn', 'huanqiu.com', 'guancha.cn', 'cls.cn', 'stcn.com',
                   'eastmoney.com', 'nbd.com.cn', '21jingji.com', 'gmw.cn', 'cnr.cn', 'youth.cn', 'cyol.com',
                   'zaobao.com', 'zaobao.com.sg', 'scmp.com', 'rfa.org', 'voachinese.com', 'bbc.com', 'dw.com'}

SPREAD_DAYS = 14           # outlets_first: outlets linking within this many days of the first link
# a corpus site counts as a news outlet if it has this many AI articles: CC-NEWS also crawls company newsrooms
# (anthropic.com, openai.com), whose posts are sources
MIN_NEWS_ARTICLES = 5000
FIRST_DAY = '2000-01-01'   # earlier link dates are bad dates
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
    """rows: link rows (dicts) from every corpus; outlets: the corpora's news outlets, so not primary sources
    (default: the rows' outlets; scripts/primary_sources.py passes those with MIN_NEWS_ARTICLES+ AI articles).
    Returns one summary per primary source, most outlets within spread_days of its first link first."""
    news = (set(outlets) if outlets is not None else {r['outlet'] for r in rows}) | NEWS_DOMAINS
    by_doc = defaultdict(list)
    for r in rows:
        if r['date'] and r['date'] >= FIRST_DAY:
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


def chinese_page_links(row, last_day):
    """(date, body hrefs) of one crawled page if it is Chinese and about AI (title or article body: config/
    chinese_ai_terms.txt), with a date (src/media_storms.py page_date) from FIRST_DAY to last_day; else None.
    Body links only (readability), so a site's menus and footers aren't counted."""
    import lxml.html
    from readability import Document
    from src.ai_mentions import about_ai_article
    from src.media_storms import is_chinese, page_date
    html = row['html'].decode('utf-8', errors='replace') if isinstance(row['html'], bytes) else row['html']
    if not html or not is_chinese(row.get('language'), html) or not about_ai_article(html):
        return None
    date = (page_date(html, row['url']) or '')[:10]
    if not (FIRST_DAY <= date <= last_day):
        return None
    try:
        body = lxml.html.fromstring(Document(html).summary())
        body.make_links_absolute(row['url'])
        hrefs = [href for _, attr, href, _ in body.iterlinks() if attr == 'href']
    except Exception:
        hrefs = []
    return date, hrefs
