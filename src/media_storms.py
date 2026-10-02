"""
Media storms in the English CC-NEWS coverage of AI, after Litterer, Jurgens & Card (2023), "When it Rains, it
Pours" (Findings of EMNLP), sec. 3.3-3.4. Logic only: no paths. Steps (scripts/media_storms.py), each building on
the last and skipping work already done:

    by_day   each WARC's embedded articles (src/news_embeddings.py) joined to their dates (src/news_pubdates.py),
             split into one small file per day: <days>/<date>/<warc>.parquet {url, outlet, title, vector}
    edges    per day d: cosine of d's articles with those of days d .. d + WINDOW_DAYS - 1; pairs >= THRESHOLD
             (the paper: < 8 days apart, cosine > 0.9; it also required a shared named entity, which we don't
             have, so the threshold alone decides)
    cluster  story clusters: connected components of the edges (union-find)
    storms   clusters lasting >= MIN_DAYS during which >= MIN_OUTLETS outlets are in "storm mode": the story is
             >= STORM_SHARE of the outlet's articles over some STORM_WINDOW-day window in which the outlet has
             >= MIN_OUTLET_ARTICLES articles. Shares are of the outlet's AI coverage (our corpus), not all its news.
"""
import datetime
import os
from collections import defaultdict

import numpy as np
import pyarrow as pa
import pyarrow.parquet as pq

from src.external_links import registered_domain

THRESHOLD = 0.9
WINDOW_DAYS = 8
BLOCK = 2048                 # rows of day d compared at a time
MIN_DAYS, MIN_OUTLETS = 7, 5
STORM_WINDOW, STORM_SHARE, MIN_OUTLET_ARTICLES = 3, 0.03, 40
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
    for date, rows in by_day.items():
        out = os.path.join(days_dir, date, warc + '.parquet')
        os.makedirs(os.path.dirname(out), exist_ok=True)
        pq.write_table(pa.Table.from_pylist(rows, DAY_SCHEMA), out + '.part')
        os.rename(out + '.part', out)
    return {date: len(rows) for date, rows in by_day.items()}


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


def day_edges(days_dir, date, threshold=THRESHOLD, window=WINDOW_DAYS):
    """Pairs (url_a, url_b, cosine) >= threshold with url_a on date and url_b on date .. date + window - 1 (same
    day: each pair once)."""
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
    edges = []
    for start in range(0, len(urls), BLOCK):
        sims = vecs[start:start + BLOCK] @ others.T
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

def storms(articles, cluster_of, min_days=MIN_DAYS, min_outlets=MIN_OUTLETS, window=STORM_WINDOW,
           share=STORM_SHARE, min_outlet_articles=MIN_OUTLET_ARTICLES):
    """articles: [{url, outlet, date}] (all of them, clustered or not). Returns one summary per storm:
    {cluster, articles, outlets, storm_outlets, first, last, days, peak}, largest first."""
    per_outlet_day = defaultdict(int)                  # (outlet, date) -> all articles
    members = defaultdict(list)
    for a in articles:
        per_outlet_day[(a['outlet'], a['date'])] += 1
        if a['url'] in cluster_of:
            members[cluster_of[a['url']]].append(a)
    found = []
    for cid, arts in members.items():
        dates = sorted(a['date'] for a in arts)
        first, last = dates[0], dates[-1]
        span = (datetime.date.fromisoformat(last) - datetime.date.fromisoformat(first)).days + 1
        outlets = {a['outlet'] for a in arts}
        if span < min_days or len(outlets) < min_outlets:
            continue
        story = defaultdict(int)                       # (outlet, date) -> this story's articles
        for a in arts:
            story[(a['outlet'], a['date'])] += 1
        in_storm = set()
        for outlet in outlets:
            for start_offset in range(-(window - 1), span):
                days_ = [shift(first, start_offset + k) for k in range(window)]
                total = sum(per_outlet_day.get((outlet, d), 0) for d in days_)
                ours = sum(story.get((outlet, d), 0) for d in days_)
                if total >= min_outlet_articles and ours / total >= share:
                    in_storm.add(outlet)
                    break
        if len(in_storm) >= min_outlets:
            by_day = defaultdict(int)
            for d in dates:
                by_day[d] += 1
            found.append({'cluster': cid, 'articles': len(arts), 'outlets': len(outlets),
                          'storm_outlets': len(in_storm), 'first': first, 'last': last, 'days': span,
                          'peak': max(by_day, key=by_day.get)})
    return sorted(found, key=lambda s: -s['articles'])
