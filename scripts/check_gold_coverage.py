#!/usr/bin/env python
"""
Where a hand-collected list of Chinese articles about one event gets lost on the way to a Chinese media storm
(the gold list: config/gold/*.csv, columns url, alt_urls, domain, outlet, in_crawled_list, date, title, and
event_leg or phase).
For each listed article (by default those from crawled outlets), stage by stage:
    crawled     in a crawl's pages.jsonl (data/interim/site_crawls/<domain>/)
    html        its HTML saved (site_crawls/<domain>/html/*.parquet)
    outcome     what the storms' by_day filter makes of it (src/media_storms.py site_crawl_page: kept, not about ai,
                no date, listing page, short, not chinese ...), rerun here on the saved HTML
    embedded    has an embedding (site_crawls/<domain>/embeddings/*.parquet)
    day         in the storms' day files (data/interim/media_storms_zh/days/<date>/), with its date
    cluster     its cluster (clusters.parquet) and the cluster's size; storm: whether that cluster is a storm
URLs are compared without scheme, www./m./wap. and trailing slashes (m.cls.cn/detail/1 = www.cls.cn/detail/1).
    -> data/processed/gold_coverage_<list name>.tsv, and a stage-by-stage summary

Run as a module from the repo root (normally: sbatch scripts/slurm/check_gold_coverage.slurm):
    python -m scripts.check_gold_coverage -gold config/gold/chinese_coverage_hf_openai_anthropic.csv
"""
import argparse
import glob
import json
import os
from collections import Counter
from urllib.parse import urlparse

import pandas as pd
import pyarrow as pa
import pyarrow.compute as pc
import pyarrow.parquet as pq

from config.paths import MEDIA_STORMS_ZH_DIR, NEWS_EN_ZH_LINKS_PATH, SITE_CRAWLS_DIR
from src.media_storms import site_crawl_page


def parse_args():
    parser = argparse.ArgumentParser(description='Where a gold list of Chinese articles is lost before the storms')
    parser.add_argument('-gold', required=True)
    parser.add_argument('-all', action='store_true', help='every listed article, not only crawled outlets')
    parser.add_argument('-crawls-dir', default=str(SITE_CRAWLS_DIR))
    parser.add_argument('-storms-dir', default=str(MEDIA_STORMS_ZH_DIR))
    return parser.parse_args()


def norm(url):
    """A URL's comparison key: host without www./m./wap., path without a trailing slash, the query kept."""
    parts = urlparse(url.strip())
    host = (parts.hostname or '').lower()
    for prefix in ('www.', 'm.', 'wap.'):
        host = host.removeprefix(prefix)
    return host + parts.path.rstrip('/') + (('?' + parts.query) if parts.query else '')


def url_files(pattern, keys):
    """{key: path of the parquet file holding it}, reading only the url column of the files matching pattern."""
    found = {}
    for path in glob.glob(pattern):
        try:
            urls = pq.read_table(path, columns=['url'])['url'].to_pylist()
        except Exception:
            continue
        for u in urls:
            k = norm(u or '')
            if k in keys and k not in found:
                found[k] = (path, u)
    return found


def main():
    args = parse_args()
    gold = pd.read_csv(args.gold, keep_default_na=False)
    if not args.all:
        gold = gold[gold['in_crawled_list'] == 'y']
    gold = gold.reset_index(drop=True)
    leg = 'event_leg' if 'event_leg' in gold else 'phase' if 'phase' in gold else None
    forms = [[u for u in [r.url] + [a.strip() for a in r.alt_urls.split(';')] if u] for r in gold.itertuples()]
    keys_of = [{norm(u) for u in f} for f in forms]
    keys = set().union(*keys_of)
    print(f'{len(gold)} listed articles ({len(keys)} URL forms) from {gold["domain"].nunique()} outlets', flush=True)

    crawled = set()
    for path in glob.glob(os.path.join(args.crawls_dir, '*', 'pages.jsonl')):
        with open(path, encoding='utf-8', errors='replace') as f:
            for line in f:
                start = line.find('"url": "') + 8
                k = norm(line[start:line.find('"', start)])
                if k in keys:
                    crawled.add(k)
    print(f'crawled: {len(crawled)} URL forms found in pages.jsonl', flush=True)
    html = url_files(os.path.join(args.crawls_dir, '*', 'html', '*.parquet'), keys)
    print(f'html: {len(html)} found', flush=True)
    embedded = url_files(os.path.join(args.crawls_dir, '*', 'embeddings', '*.parquet'), keys)
    print(f'embedded: {len(embedded)} found', flush=True)
    days = {}
    for path in glob.glob(os.path.join(args.storms_dir, 'days', '*', '*.parquet')):
        for u in pq.read_table(path, columns=['url'])['url'].to_pylist():
            if norm(u) in keys:
                days[norm(u)] = (os.path.basename(os.path.dirname(path)), u)
    clusters = pq.read_table(os.path.join(args.storms_dir, 'clusters.parquet')).to_pandas()
    size = clusters['cluster'].value_counts()
    cluster_of = {norm(u): c for u, c in zip(clusters['url'], clusters['cluster'])}
    with open(os.path.join(args.storms_dir, 'storms.jsonl'), encoding='utf-8') as f:
        storms = {json.loads(line)['cluster'] for line in f if line.strip()}

    outcomes = {}                              # the by_day filter, rerun on the saved HTML of the listed pages
    by_file = {}
    for k, (path, u) in html.items():
        by_file.setdefault(path, []).append(u)
    for path, urls in by_file.items():
        table = pq.read_table(path, columns=['url', 'language', 'html'])
        for row in table.filter(pc.is_in(table['url'], pa.array(urls))).to_pylist():
            try:
                outcome, _ = site_crawl_page(row, '9999-12-31')
            except Exception as e:
                outcome = f'error: {type(e).__name__}'
            outcomes[norm(row['url'])] = outcome

    rows = []
    for r, ks in zip(gold.itertuples(), keys_of):
        def first(found):
            return next((found[k] for k in ks if k in found), None)
        k_cluster = next((cluster_of[k] for k in ks if k in cluster_of), None)
        rows.append({'url': r.url, 'outlet': r.outlet, 'date': r.date, 'leg': getattr(r, leg) if leg else '',
                     'title': r.title,
                     'crawled': any(k in crawled for k in ks), 'html': first(html) is not None,
                     'outcome': next((outcomes[k] for k in ks if k in outcomes), ''),
                     'embedded': first(embedded) is not None, 'day': (first(days) or ('',))[0],
                     'cluster': k_cluster or '', 'cluster_size': int(size.get(k_cluster, 0)) if k_cluster else 0,
                     'storm': bool(k_cluster and k_cluster in storms)})
    table = pd.DataFrame(rows)
    name = os.path.splitext(os.path.basename(args.gold))[0]
    out = os.path.join(os.path.dirname(str(NEWS_EN_ZH_LINKS_PATH)), f'gold_coverage_{name}.tsv')
    table.to_csv(out, sep='\t', index=False)

    n = len(table)
    print(f'\nstage by stage, of {n} listed articles:')
    for stage, count in (('crawled (pages.jsonl)', table['crawled'].sum()), ('html saved', table['html'].sum()),
                         ('kept by the by_day filter', (table['outcome'] == 'kept').sum()),
                         ('embedded', table['embedded'].sum()), ('in the day files', (table['day'] != '').sum()),
                         ('in a cluster', (table['cluster'] != '').sum()), ('in a storm', table['storm'].sum())):
        print(f'  {count:4d}  {stage}')
    print('by_day outcomes of the saved ones:', dict(Counter(table.loc[table['html'], 'outcome'])))
    print('not crawled, by outlet:', table.loc[~table['crawled'], 'outlet'].value_counts().head(10).to_dict())
    in_clusters = table[table['cluster'] != '']
    print(f'{in_clusters["cluster"].nunique()} distinct clusters hold them; sizes:',
          in_clusters.drop_duplicates('cluster')['cluster_size'].value_counts().sort_index().to_dict())
    print(f'-> {out}')


if __name__ == '__main__':
    main()
