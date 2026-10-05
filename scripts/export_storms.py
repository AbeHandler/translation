#!/usr/bin/env python
"""
Export the media storms (scripts/media_storms.py) for reading: -top storms, those most focused on one cited
document first (seed_share: the share of the storm's articles linking to its top cited document; the seeds step),
then the rest, largest first. Each with its cited documents, articles per day, top outlets, and up to -max-articles
of its articles (url, outlet, date, title, cites_seed; the citing ones first, then a sample over its days).
    data/interim/media_storms/{storms.jsonl, storm_seeds.jsonl, clusters.parquet, days/}
        -> data/processed/storms_review.json
Small enough to copy to a laptop and read (or load into a review page).

Run as a module from the repo root:
    python -m scripts.export_storms
    python -m scripts.export_storms -top 1000 -max-articles 40
    python -m scripts.export_storms -corpus zh          # -> data/processed/storms_review_zh.json
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

from config.paths import MEDIA_STORMS_DIR, MEDIA_STORMS_ZH_DIR, NEWS_EN_ZH_LINKS_PATH


def parse_args():
    parser = argparse.ArgumentParser(description='Export the media storms for reading')
    parser.add_argument('-corpus', default='en', choices=('en', 'zh'), help='zh: the Chinese site crawls\' storms')
    parser.add_argument('-storms-dir', default=None, help='default: by corpus')
    parser.add_argument('-top', type=int, default=500, help='this many storms')
    parser.add_argument('-max-articles', type=int, default=60, help='per storm')
    parser.add_argument('-max-citing', type=int, default=20, help='per storm: citing articles shown first')
    parser.add_argument('-out', default=None, help='default: data/processed/storms_review[_zh].json')
    args = parser.parse_args()
    zh = args.corpus == 'zh'
    args.storms_dir = args.storms_dir or str(MEDIA_STORMS_ZH_DIR if zh else MEDIA_STORMS_DIR)
    args.out = args.out or os.path.join(os.path.dirname(str(NEWS_EN_ZH_LINKS_PATH)),
                                        'storms_review_zh.json' if zh else 'storms_review.json')
    return args


def main():
    args = parse_args()
    start = time.time()

    def say(msg):
        print(f'[{time.time() - start:6.0f}s] {msg}', flush=True)

    with open(os.path.join(args.storms_dir, 'storm_seeds.jsonl'), encoding='utf-8') as f:
        seeds = {row['cluster']: row for row in map(json.loads, f)}
    with open(os.path.join(args.storms_dir, 'storms.jsonl'), encoding='utf-8') as f:
        storms = [json.loads(line) for line in f]
    storms = sorted(storms, key=lambda s: (-seeds[s['cluster']]['seed_share'], -s['articles']))[:args.top]
    if not storms:
        raise SystemExit(f'no storms in {args.storms_dir}/storms.jsonl: nothing to export (see the storms step\'s log)')
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
        seed = seeds[s['cluster']]
        citing = set(seed['citing'])
        articles = sorted(({**a, 'cites_seed': a['url'] in citing} for a in members[s['cluster']]),
                          key=lambda a: a['date'])
        per_day = Counter(a['date'] for a in articles)
        cite = [a for a in articles if a['cites_seed']]
        cite = rng.sample(cite, min(len(cite), args.max_citing))
        rest = [a for a in articles if not a['cites_seed']]
        rest = rng.sample(rest, min(len(rest), args.max_articles - len(cite)))
        out.append({**{k: v for k, v in s.items() if k != 'articles'}, 'n_articles': s['articles'],
                    'seed_share': seed['seed_share'], 'n_citing': len(citing), 'seeds': seed['seeds'],
                    'per_day': dict(sorted(per_day.items())),
                    'top_outlets': Counter(a['outlet'] for a in articles).most_common(15),
                    'articles': sorted(cite + rest, key=lambda a: a['date'])})
    with open(args.out, 'w', encoding='utf-8') as f:
        json.dump(out, f, ensure_ascii=False)
    print(f'{len(out)} storms, {sum(len(s["articles"]) for s in out)} articles -> {args.out}')
    for s in out[:15]:
        top = s['seeds'][0]['href'][:70] if s['seeds'] else '-'
        print(f"  {s['seed_share']:.2f} of {s['n_articles']:5} articles cite {top}  |  {s.get('title', '')[:50]}")


if __name__ == '__main__':
    main()
