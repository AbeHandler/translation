#!/usr/bin/env python
"""
Export the media storms (scripts/media_storms.py) for reading: the -top largest storms, each with its articles
(url, outlet, date, title; up to -max-articles, spread over the storm's days) and its articles per day.
    data/interim/media_storms/{storms.jsonl, clusters.parquet, days/} -> data/processed/storms_review.json
Small enough to copy to a laptop and read (or load into a review page).

Run as a module from the repo root:
    python -m scripts.export_storms
    python -m scripts.export_storms -top 200
"""
import argparse
import glob
import json
import os
import random
import time
from collections import Counter, defaultdict

import pyarrow as pa
import pyarrow.compute as pc
import pyarrow.parquet as pq

from config.paths import MEDIA_STORMS_DIR, NEWS_EN_ZH_LINKS_PATH


def parse_args():
    parser = argparse.ArgumentParser(description='Export the media storms for reading')
    parser.add_argument('-storms-dir', default=str(MEDIA_STORMS_DIR))
    parser.add_argument('-top', type=int, default=100, help='this many storms, largest first')
    parser.add_argument('-max-articles', type=int, default=150, help='per storm')
    parser.add_argument('-out', default=os.path.join(os.path.dirname(str(NEWS_EN_ZH_LINKS_PATH)),
                                                     'storms_review.json'))
    return parser.parse_args()


def main():
    args = parse_args()
    start = time.time()

    def say(msg):
        print(f'[{time.time() - start:6.0f}s] {msg}', flush=True)

    with open(os.path.join(args.storms_dir, 'storms.jsonl'), encoding='utf-8') as f:
        storms = [json.loads(line) for line in f][:args.top]
    wanted = {s['cluster'] for s in storms}
    say(f'{len(storms)} storms to export')
    clusters = pq.read_table(os.path.join(args.storms_dir, 'clusters.parquet'))
    clusters = clusters.filter(pc.is_in(clusters['cluster'], pa.array(sorted(wanted), clusters['cluster'].type)))
    cluster_of = dict(zip(clusters['url'].to_pylist(), clusters['cluster'].to_pylist()))
    urls = pa.array(list(cluster_of), pa.string())
    say(f'{len(cluster_of)} articles in them; finding them in the day files')
    paths = glob.glob(os.path.join(args.storms_dir, 'days', '*', '*.parquet'))
    members, seen = defaultdict(list), set()
    for n, path in enumerate(paths, 1):
        date = os.path.basename(os.path.dirname(path))
        table = pq.read_table(path, columns=['url', 'outlet', 'title'])
        for row in table.filter(pc.is_in(table['url'], urls)).to_pylist():   # only the storms' articles
            if row['url'] not in seen:
                seen.add(row['url'])
                members[cluster_of[row['url']]].append({**row, 'date': date})
        if n % 2000 == 0 or n == len(paths):
            say(f'{n}/{len(paths)} day files read, {len(seen)}/{len(cluster_of)} articles found')
    rng = random.Random(0)
    out = []
    for s in storms:
        articles = sorted(members[s['cluster']], key=lambda a: a['date'])
        per_day = Counter(a['date'] for a in articles)
        sample = articles if len(articles) <= args.max_articles else sorted(
            rng.sample(articles, args.max_articles), key=lambda a: a['date'])
        out.append({**{k: v for k, v in s.items() if k != 'articles'}, 'n_articles': s['articles'],
                    'per_day': dict(sorted(per_day.items())),
                    'top_outlets': Counter(a['outlet'] for a in articles).most_common(15), 'articles': sample})
    with open(args.out, 'w', encoding='utf-8') as f:
        json.dump(out, f, ensure_ascii=False)
    print(f'{len(out)} storms, {sum(len(s["articles"]) for s in out)} articles -> {args.out}')
    for s in out[:10]:
        print(f"  {s['n_articles']:5} articles, {s['storm_outlets']:3} outlets in storm mode, "
              f"{s['first']}..{s['last']}  {s.get('title', '')[:70]}")


if __name__ == '__main__':
    main()
