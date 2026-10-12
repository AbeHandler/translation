#!/usr/bin/env python
"""
URL lists for the crawler's list mode (scrapy/slurm/fetch_urls.slurm), for articles a crawl can't reach:
    -gold LIST        the listed articles of crawled outlets (url and alt_urls), per site
    -from/-to         for sites that number their articles (src/crawl_ids.py: ithome, jiemian, yicai, tmtpost): every
                      article ID published in the window, found by binary search over the IDs (each probe fetches a
                      page and reads its date); -to past the newest article stops at the latest ID
-> data/interim/site_crawls/<domain>/urls/<name>.txt per site, and the sbatch line to fetch each.

Run as a module from the repo root (needs the internet: a login node, or a laptop and then copy the lists):
    python -m scripts.make_crawl_urls -name hf_hack -gold config/gold/chinese_coverage_hf_openai_anthropic.csv \\
        -from 2026-07-16 -to 2026-10-08
    python -m scripts.make_crawl_urls -name r1 -gold config/gold/chinese_coverage_deepseek_r1.csv \\
        -from 2025-01-15 -to 2025-02-20 -sites ithome.com,jiemian.com
"""
import argparse
import os
import time
from collections import defaultdict

import pandas as pd
import requests

from config.paths import SITE_CRAWLS_DIR
from src.crawl_ids import SITES, IdProber, id_of, urls_for
from src.extract_pubdate import extract_pubdate

HEADERS = {'User-Agent': 'Mozilla/5.0 (research crawler; abha4861@colorado.edu)'}


def parse_args():
    parser = argparse.ArgumentParser(description='URL lists for the crawler list mode')
    parser.add_argument('-name', required=True, help='the lists\' file name')
    parser.add_argument('-gold', default=None, help='a gold list: its listed articles, per site')
    parser.add_argument('-from', dest='start', default=None, help='with -to: number-range lists for the window')
    parser.add_argument('-to', dest='end', default=None)
    parser.add_argument('-sites', default=','.join(SITES), help='numbered sites to range over')
    parser.add_argument('-crawls-dir', default=str(SITE_CRAWLS_DIR))
    parser.add_argument('-delay', type=float, default=0.3, help='seconds between probes (politeness)')
    return parser.parse_args()


def main():
    args = parse_args()
    lists = defaultdict(set)
    known = defaultdict(list)          # IDs of listed articles: where the binary searches start
    if args.gold:
        gold = pd.read_csv(args.gold, keep_default_na=False)
        gold = gold[gold['in_crawled_list'] == 'y']
        for row in gold.itertuples():
            for url in [row.url] + [u.strip() for u in row.alt_urls.split(';') if u.strip()]:
                lists[row.domain].add(url)
                if row.domain in SITES and id_of(row.domain, url):
                    known[row.domain].append(id_of(row.domain, url))
        print(f'{len(gold)} listed articles of crawled outlets, {sum(map(len, lists.values()))} URLs')

    if args.start and args.end:
        def fetch(url):
            time.sleep(args.delay)
            try:
                r = requests.get(url, headers=HEADERS, timeout=20)
                return r.status_code, r.text
            except requests.RequestException:
                return 0, ''

        def date_of(html, url):
            try:
                return extract_pubdate(html, url, extensive=False)[0]
            except Exception:
                return None
        for site in args.sites.split(','):
            if not known[site]:
                print(f'{site}: no known article ID to start from (give a -gold list with one): skipped')
                continue
            prober = IdProber(site, fetch, date_of)
            anchor = min(known[site])
            latest = prober.latest(max(known[site]))
            lo = prober.first_on_or_after(args.start, max(anchor - 2_000_000, 1), anchor)
            after_end = prober.first_on_or_after(args.end + 'z', lo, latest + prober.window)   # 'z': after the day
            hi = min(after_end, latest + prober.window)
            ids = range(lo, hi + 1)
            for k in ids:
                lists[site].update(urls_for(site, k))
            print(f'{site}: IDs {lo}..{hi} ({len(ids)} IDs, {len(ids) * len(SITES[site])} URLs) for '
                  f'{args.start}..{args.end}; latest ID about {latest}; {len(prober.cache)} probes', flush=True)

    print('\nlists:')
    for site, urls in sorted(lists.items()):
        folder = os.path.join(args.crawls_dir, site, 'urls')
        os.makedirs(folder, exist_ok=True)
        path = os.path.join(folder, f'{args.name}.txt')
        with open(path, 'w', encoding='utf-8') as f:
            f.write('\n'.join(sorted(urls)) + '\n')
        print(f'  {len(urls):7d}  sbatch --export=DOMAIN={site},URLS_FILE={path} scrapy/slurm/fetch_urls.slurm')


if __name__ == '__main__':
    main()
