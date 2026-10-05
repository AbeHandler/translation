"""
Media storms in news coverage of AI, after Litterer, Jurgens & Card (2023), "When it Rains, it Pours" (Findings
of EMNLP), sec. 3.3-3.4. Two corpora, the same steps after by_day: the English CC-NEWS articles (newsSimilarity
embeddings, CC-NEWS's US-centred outlets) and the Chinese site crawls (the mainland outlets in config/sites.txt;
bge-base-zh-v1.5 embeddings, a general-purpose Chinese document embedder, already made for every crawled page by
scripts/embed_site_crawls.py). Logic only: no paths. Steps (scripts/media_storms.py), each building on the last
and skipping work already done:

    by_day   each WARC's embedded articles (src/news_embeddings.py) joined to their dates (src/news_pubdates.py),
             split into one small file per day: <days>/<date>/<warc>.parquet {url, outlet, title, vector}.
             Chinese: each crawled HTML file's Chinese pages about AI (src/ai_mentions.py about_ai_article), their
             embeddings and publication dates (extract_pubdate) -> <days>/<date>/<domain>__<part>.parquet, and
             their links -> <links>/<domain>__<part>.jsonl (the cc_links format, for seeds)
    edges    per day d: cosine of d's articles with those of days d .. d + WINDOW_DAYS - 1; pairs >= THRESHOLD
             (the paper: < 8 days apart, cosine > 0.9; it also required a shared named entity, which we don't
             have, so the threshold alone decides)
    cluster  story clusters: connected components of the edges (union-find)
    storms   clusters lasting >= MIN_DAYS during which >= MIN_OUTLETS outlets are in "storm mode": the story is
             >= STORM_SHARE of the outlet's articles over some STORM_WINDOW-day window in which the outlet has
             >= MIN_OUTLET_ARTICLES articles. Shares are of the outlet's AI coverage (our corpus), not all its news.
             A storm also hits and subsides: >= MIN_PEAK_SHARE of its articles fall within PEAK_HALF days of its
             peak. This drops template streams (daily crypto prices, stock-holding notices) that chain into one
             year-long cluster: their peak week holds 2-13% of their articles, real storms' 41-100%.
    seeds    the documents each storm cites: the external links of its articles (cc_links), counted per storm.
             A storm focused on one document (a model release, an executive order) has a top cited document
             linked by a large share of its articles (seed_share). Links found in many storms (homepages, social
             profiles, share buttons) are left out.
"""
import datetime
import json
import os
import re
from collections import Counter, defaultdict
from urllib.parse import urlparse

import numpy as np
import pyarrow as pa
import pyarrow.parquet as pq

from src.external_links import registered_domain

FIRST_DAY = '2023-01-01'     # publication dates before this (or after the crawl) are taken to be wrong
MIN_TEXT_CHARS = 300         # Chinese crawls: shorter pages are market flashes, captions or listings, not articles
LISTING = re.compile(r'第\s*\d+\s*页|最新资讯|最新进展')   # channel and listing pages ("人工智能 第22页")
THRESHOLD = 0.9
THRESHOLD_ZH = 0.85     # bge-base-zh, cross-outlet pairs only: rewritten coverage of one story rarely reaches 0.9
WINDOW_DAYS = 8
BLOCK = 2048                 # rows of day d compared at a time
MIN_DAYS, MIN_OUTLETS = 7, 5
STORM_WINDOW, STORM_SHARE, MIN_OUTLET_ARTICLES = 3, 0.03, 40
MIN_PEAK_SHARE, PEAK_HALF = 0.3, 3
SEED_MAX_STORMS = 5          # a link cited in more storms than this is generic (a homepage, a profile), not a seed
SEED_MIN_ARTICLES = 3        # a seed is cited by at least this many of the storm's articles
# a storm whose top cited document is on one of these is a burst of templated stock notices (price targets,
# holdings), all linking the stock's page: not news
TEMPLATE_HOSTS = ('marketbeat.com',)
DAY_SCHEMA = pa.schema([('url', pa.string()), ('outlet', pa.string()), ('title', pa.string()),
                        ('vector', pa.list_(pa.float16()))])
EDGE_SCHEMA = pa.schema([('a', pa.string()), ('b', pa.string()), ('cosine', pa.float32())])


# by_day

def split_by_day(embeddings_path, dates_path, days_dir, warc):
    """Write the WARC's articles into <days_dir>/<date>/<warc>.parquet, one file per day it has articles for.
    Articles without a date are left out. Returns {day: count}."""
    dates = {r['url']: r['date'] for r in pq.read_table(dates_path, columns=['url', 'date']).to_pylist()}
    by_day = defaultdict(list)
    for row in pq.read_table(embeddings_path, columns=['url', 'title', 'embedding']).to_pylist():
        date = dates.get(row['url'])
        if date:
            by_day[date].append({'url': row['url'], 'outlet': registered_domain(row['url']), 'title': row['title'],
                                 'vector': row['embedding']})
    return write_days(by_day, days_dir, warc)


def write_days(by_day, days_dir, key):
    """{date: [day rows]} -> <days_dir>/<date>/<key>.parquet each. Returns {day: count}."""
    for date, rows in by_day.items():
        out = os.path.join(days_dir, date, key + '.parquet')
        os.makedirs(os.path.dirname(out), exist_ok=True)
        pq.write_table(pa.Table.from_pylist(rows, DAY_SCHEMA), out + '.part')
        os.rename(out + '.part', out)
    return {date: len(rows) for date, rows in by_day.items()}


def is_chinese(language, html):
    """The page's title has MIN_TITLE_CJK+ Chinese characters; for a page without a title, news-please's language.
    The title decides because the crawls' recorded language proved unreliable (it rejected every page)."""
    match = TITLE.search(html)
    title = match.group(1) if match else ''
    if title.strip():
        return len(CJK.findall(title)) >= MIN_TITLE_CJK
    return bool(language) and language.lower().startswith('zh')


MIN_TITLE_CJK = 4
TITLE = re.compile(r'<title[^>]*>(.*?)</title>', re.I | re.S)
CJK = re.compile(r'[\u4e00-\u9fff]')


def page_date(html, url):
    """The page's publication date: newspaper4k, then htmldate's quick search, then its extensive one (slower,
    so only for the pages that need it), then a date in the URL (/2025/01/20/, /20250120/, /2025-01/20/)."""
    from src.extract_pubdate import extract_pubdate
    found = extract_pubdate(html, url, extensive=True)[0]
    if found:
        return found
    match = URL_DATE.search(url)
    return f'{match.group(1)}-{match.group(2)}-{match.group(3)}' if match else None


URL_DATE = re.compile(r'/(20[2-3]\d)[-/]?(0[1-9]|1[0-2])[-/]?(0[1-9]|[12]\d|3[01])(?:/|\D)')


def site_crawl_page(row, last_day, pubdate=None, about=None):
    """(outcome, found): outcome is 'kept' and found (date, day row without vector, links) for a crawled page
    that is Chinese, about AI and dated between FIRST_DAY and last_day; otherwise outcome says which test it
    failed ('empty', 'not chinese', 'listing page', 'not about ai', 'no date', 'date out of range') and found is None.
    pubdate(html, url) -> date string; about(html) -> bool (injectable)."""
    import lxml.html
    from src.ai_mentions import about_ai_article
    pubdate = pubdate or page_date
    about = about or about_ai_article
    html = row['html'].decode('utf-8', errors='replace') if isinstance(row['html'], bytes) else row['html']
    if not html:
        return 'empty', None
    if not is_chinese(row.get('language'), html):
        return 'not chinese', None
    match = TITLE.search(html)
    if match and LISTING.search(match.group(1)):
        return 'listing page', None
    if not about(html):
        return 'not about ai', None
    date = (pubdate(html, row['url']) or '')[:10]
    if not date:
        return 'no date', None
    if not (FIRST_DAY <= date <= last_day):
        return 'date out of range', None
    try:
        tree = lxml.html.fromstring(html)
        tree.make_links_absolute(row['url'])
        title = (tree.findtext('.//title') or '').strip()
        links = [{'href': href} for _, attr, href, _ in tree.iterlinks() if attr == 'href']
    except Exception:
        title, links = '', []
    return 'kept', (date, {'url': row['url'], 'outlet': registered_domain(row['url']), 'title': title}, links)


def split_site_crawl_by_day(html_path, embeddings_path, days_dir, links_path, key, last_day, **page_kwargs):
    """One crawled HTML file's Chinese AI pages -> <days_dir>/<date>/<key>.parquet (with their embeddings) and
    links_path (one {url, links: [{href}]} line per page, the cc_links format). Returns ({day: count}, funnel):
    funnel counts the pages by outcome ('no embedding', site_crawl_page's), so a file that keeps nothing says why."""
    rows = pq.read_table(embeddings_path, columns=['url', 'text_chars', 'embedding']).to_pylist()
    vectors = {r['url']: r['embedding'] for r in rows if r['embedding'] is not None}
    short = {r['url'] for r in rows if r['embedding'] is not None and r['text_chars'] < MIN_TEXT_CHARS}
    by_day, funnel = defaultdict(list), Counter()
    with open(links_path + '.part', 'w', encoding='utf-8') as f:
        for batch in pq.ParquetFile(html_path).iter_batches(batch_size=200, columns=['url', 'language', 'html']):
            for row in batch.to_pylist():
                if row['url'] not in vectors:
                    funnel['no embedding'] += 1
                    continue
                if row['url'] in short:
                    funnel['short'] += 1
                    continue
                outcome, found = site_crawl_page(row, last_day, **page_kwargs)
                funnel[outcome] += 1
                if found:
                    date, day_row, links = found
                    by_day[date].append({**day_row, 'vector': vectors[row['url']]})
                    f.write(json.dumps({'url': row['url'], 'links': links}, ensure_ascii=False) + '\n')
    counts = write_days(by_day, days_dir, key)
    os.rename(links_path + '.part', links_path)
    return counts, dict(funnel)


def read_day(days_dir, date):
    """(urls, vectors as float32 (n, d)) of one day, each URL once (an article can be in several WARCs)."""
    folder = os.path.join(days_dir, date)
    if not os.path.isdir(folder):
        return [], np.zeros((0, 0), dtype=np.float32)
    seen, urls, vecs = set(), [], []
    for name in sorted(os.listdir(folder)):
        if not name.endswith('.parquet'):
            continue
        for row in pq.read_table(os.path.join(folder, name), columns=['url', 'vector']).to_pylist():
            if row['url'] not in seen:
                seen.add(row['url'])
                urls.append(row['url'])
                vecs.append(row['vector'])
    return urls, np.asarray(vecs, dtype=np.float32).reshape(len(urls), -1)


# edges

def shift(date, days):
    return (datetime.date.fromisoformat(date) + datetime.timedelta(days=days)).isoformat()


def day_edges(days_dir, date, threshold=THRESHOLD, window=WINDOW_DAYS, cross_outlet=False):
    """Pairs (url_a, url_b, cosine) >= threshold with url_a on date and url_b on date .. date + window - 1 (same
    day: each pair once). cross_outlet: only pairs from different outlets (the Chinese crawls: one site's own
    templated pages, like market flashes or listing pages, are near-identical and chain into year-long clusters;
    a storm is coverage across outlets)."""
    urls, vecs = read_day(days_dir, date)
    if not urls:
        return []
    later_urls, later_vecs = [], []
    for k in range(1, window):
        u, v = read_day(days_dir, shift(date, k))
        if u:
            later_urls += u
            later_vecs.append(v)
    other_urls = urls + later_urls
    others = np.vstack([vecs] + later_vecs)
    if cross_outlet:
        outlet_ids = {}
        codes = np.array([outlet_ids.setdefault(registered_domain(u), len(outlet_ids)) for u in other_urls])
    edges = []
    for start in range(0, len(urls), BLOCK):
        sims = vecs[start:start + BLOCK] @ others.T
        if cross_outlet:
            sims[codes[start:start + BLOCK, None] == codes[None, :]] = -1
        rows, cols = np.nonzero(sims >= threshold)
        for i, j in zip(rows, cols):
            if j < len(urls) and j <= start + i:   # same day: each pair once, no self-pairs
                continue
            edges.append((urls[start + i], other_urls[j], float(sims[i, j])))
    return edges


def write_edges(edges, path):
    table = pa.Table.from_pylist([{'a': a, 'b': b, 'cosine': c} for a, b, c in edges], EDGE_SCHEMA)
    pq.write_table(table, path + '.part')
    os.rename(path + '.part', path)


# cluster

class UnionFind:
    def __init__(self):
        self.parent = {}

    def root(self, x):
        self.parent.setdefault(x, x)
        while self.parent[x] != x:
            self.parent[x] = self.parent[self.parent[x]]
            x = self.parent[x]
        return x

    def union(self, a, b):
        ra, rb = self.root(a), self.root(b)
        if ra != rb:
            self.parent[max(ra, rb)] = min(ra, rb)


def clusters(edge_paths):
    """{url: cluster id (its component's smallest url)} for every url in an edge."""
    uf = UnionFind()
    for path in edge_paths:
        for a, b in zip(*pq.read_table(path, columns=['a', 'b']).to_pydict().values()):
            uf.union(a, b)
    return {url: uf.root(url) for url in uf.parent}


# storms

def peak_share(by_day, peak, half=PEAK_HALF):
    """Share of the articles within half days of the peak day."""
    near = sum(n for d, n in by_day.items()
               if abs((datetime.date.fromisoformat(d) - datetime.date.fromisoformat(peak)).days) <= half)
    return near / sum(by_day.values())


def storms(articles, cluster_of, min_days=MIN_DAYS, min_outlets=MIN_OUTLETS, window=STORM_WINDOW,
           share=STORM_SHARE, min_outlet_articles=MIN_OUTLET_ARTICLES, min_peak_share=MIN_PEAK_SHARE, funnel=None):
    """articles: [{url, outlet, date}] (all of them, clustered or not). Returns one summary per storm:
    {cluster, articles, outlets, storm_outlets, first, last, days, peak, peak_share}, largest first.
    funnel (a Counter, optional) counts the clusters that pass each test in turn, to show which one stops them."""
    per_outlet_day, members = outlet_days(articles, cluster_of)
    funnel = Counter() if funnel is None else funnel
    found = []
    for cid, arts in members.items():
        funnel['1 clusters'] += 1
        if len({a['outlet'] for a in arts}) < min_outlets:
            continue
        funnel[f'2 with >= {min_outlets} outlets'] += 1
        p = profile(arts, per_outlet_day, window, share, min_outlet_articles)
        if p['days'] < min_days:
            continue
        funnel[f'3 lasting >= {min_days} days'] += 1
        if p['storm_outlets'] < min_outlets:
            continue
        funnel[f'4 with >= {min_outlets} outlets in storm mode'] += 1
        if p['peak_share'] < min_peak_share:
            continue
        funnel[f'5 bursting (>= {min_peak_share:.0%} near the peak)'] += 1
        found.append({'cluster': cid, **p})
    return sorted(found, key=lambda s: -s['articles'])


def outlet_days(articles, cluster_of):
    """({(outlet, date): all its articles}, {cluster: [its articles]})."""
    per_outlet_day, members = defaultdict(int), defaultdict(list)
    for a in articles:
        per_outlet_day[(a['outlet'], a['date'])] += 1
        if a['url'] in cluster_of:
            members[cluster_of[a['url']]].append(a)
    return per_outlet_day, members


def profile(arts, per_outlet_day, window=STORM_WINDOW, share=STORM_SHARE, min_outlet_articles=MIN_OUTLET_ARTICLES):
    """One cluster's {articles, outlets, storm_outlets, first, last, days, peak, peak_share}. An outlet is in storm
    mode if, over some window-day stretch of the story, it published >= min_outlet_articles articles and the story
    was >= share of them."""
    dates = sorted(a['date'] for a in arts)
    first, last = dates[0], dates[-1]
    span = (datetime.date.fromisoformat(last) - datetime.date.fromisoformat(first)).days + 1
    outlets = {a['outlet'] for a in arts}
    story = Counter((a['outlet'], a['date']) for a in arts)
    in_storm = set()
    for outlet in outlets:
        for start_offset in range(-(window - 1), span):
            days_ = [shift(first, start_offset + k) for k in range(window)]
            total = sum(per_outlet_day.get((outlet, d), 0) for d in days_)
            ours = sum(story.get((outlet, d), 0) for d in days_)
            if total >= min_outlet_articles and ours / total >= share:
                in_storm.add(outlet)
                break
    by_day = Counter(dates)
    peak = max(by_day, key=by_day.get)
    return {'articles': len(arts), 'outlets': len(outlets), 'storm_outlets': len(in_storm), 'first': first,
            'last': last, 'days': span, 'peak': peak, 'peak_share': round(peak_share(by_day, peak), 3)}


# seeds

def document_key(href):
    """A cited document's key: host without www., path without a trailing slash, no query or fragment; None for
    links that can't be a document (a homepage, a share button, not http)."""
    parts = urlparse(href.strip())
    host, path = (parts.hostname or '').removeprefix('www.').removeprefix('mobile.'), parts.path.rstrip('/')
    host = 'x.com' if host == 'twitter.com' else host   # one post, two hosts
    if parts.scheme not in ('http', 'https') or not host or not path or '/hub/' in path:   # AP topic pages
        return None
    if any(t in href for t in ('sharer', 'intent/tweet', 'share?', 'shareArticle', '/share/', 'mailto:')):
        return None
    return host + path


def storm_seeds(members, links_of, max_storms=SEED_MAX_STORMS, min_articles=SEED_MIN_ARTICLES, top=5):
    """members: {cluster: [article url]}; links_of: {article url: [external hrefs]}. Returns {cluster: {seeds:
    [{document, href, articles, outlets, share}] (top cited documents, most cited first), seed_share (the top
    one's share of the storm's articles; 0 if none is cited by min_articles), citing: [article urls citing it],
    template: its top cited document is on a TEMPLATE_HOSTS site}}.
    Documents cited in more than max_storms storms are generic and left out."""
    cites = {}                                    # cluster -> document -> set of article urls
    href_of = {}
    for cid, urls in members.items():
        docs = defaultdict(set)
        for url in urls:
            for href in links_of.get(url, ()):
                key = document_key(href)
                if key:
                    docs[key].add(url)
                    href_of.setdefault(key, href)
        cites[cid] = docs
    n_storms = Counter(doc for docs in cites.values() for doc in docs)
    out = {}
    for cid, docs in cites.items():
        n = len(members[cid])
        ranked = sorted(((doc, arts) for doc, arts in docs.items() if n_storms[doc] <= max_storms),
                        key=lambda kv: -len(kv[1]))[:top]
        seeds = [{'document': doc, 'href': href_of[doc], 'articles': len(arts),
                  'outlets': len({registered_domain(u) for u in arts}), 'share': round(len(arts) / n, 3)}
                 for doc, arts in ranked]
        best = ranked[0][1] if ranked and len(ranked[0][1]) >= min_articles else set()
        template = bool(ranked) and ranked[0][0].split('/')[0].endswith(TEMPLATE_HOSTS)
        out[cid] = {'seeds': seeds, 'seed_share': round(len(best) / n, 3) if best else 0.0, 'citing': sorted(best),
                    'template': template}
    return out
