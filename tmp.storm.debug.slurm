#!/bin/bash
# Why the Chinese media storms are empty: read-only diagnostics of data/interim/media_storms_zh (nothing is written).
#   1. what each stage left: crawl files split, page outcomes, articles per day and per outlet, edges, clusters
#   2. cross-outlet similarity on 20 random days: how many pairs each threshold would keep (now 0.85)
#   3. the storm tests with today's settings (the funnel), then looser settings: how many storms each finds
#   4. the largest clusters: articles, outlets, days, titles
#
# Usage (from the repo root):
#   sbatch tmp.storm.debug.slurm        # then: cat logs/scripts/slurm/tmp.storm.debug_<jobid>.out

#SBATCH --partition=acpu
#SBATCH --time=02:00:00
#SBATCH --job-name=tmp.storm.debug
#SBATCH --output=logs/scripts/slurm/%x_%j.out
#SBATCH --mem=32G
#SBATCH --qos=cpu-normal
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --mail-type=FAIL
#SBATCH --mail-user=abha4861@colorado.edu

set -eo pipefail  # no -u: ~/.myrc and conda activate reference unset vars
source ~/.myrc
module load anaconda
conda activate translation

python - <<'PY'
import glob, json, os, random
from collections import Counter

import pyarrow.parquet as pq

from config.paths import MEDIA_STORMS_ZH_DIR, SITE_CRAWLS_DIR
from src.media_storms import (MIN_DAYS, MIN_OUTLETS, MIN_PEAK_SHARE, STORM_SHARE, THRESHOLD_ZH, day_edges,
                              daily_totals, profile, storms)

D = str(MEDIA_STORMS_ZH_DIR)
print(f'=== 1. stages in {D}')
html = glob.glob(os.path.join(str(SITE_CRAWLS_DIR), '*', 'html', '*.parquet'))
emb = [p for p in html if os.path.exists(os.path.join(os.path.dirname(os.path.dirname(p)), 'embeddings',
                                                      os.path.basename(p)))]
markers = glob.glob(os.path.join(D, 'by_day_done', '*.json'))
print(f'crawl html files {len(html)}, with embeddings {len(emb)}, split by day {len(markers)}')
pages = Counter()
for m in markers:
    pages.update(json.load(open(m)).get('pages', {}))
print('page outcomes (by_day):', dict(pages.most_common()))

articles, titles, seen = [], {}, set()
for path in glob.glob(os.path.join(D, 'days', '*', '*.parquet')):
    date = os.path.basename(os.path.dirname(path))
    for row in pq.read_table(path, columns=['url', 'outlet', 'title']).to_pylist():
        if row['url'] not in seen:
            seen.add(row['url'])
            articles.append({'url': row['url'], 'outlet': row['outlet'], 'date': date})
            titles[row['url']] = row['title']
per_day = Counter(a['date'] for a in articles)
days = sorted(per_day)
print(f'{len(articles)} articles on {len(days)} days ({days[0] if days else "-"} .. {days[-1] if days else "-"}); '
      f'per day: median {sorted(per_day.values())[len(per_day) // 2] if per_day else 0}, max {max(per_day.values(), default=0)}')
by_month = Counter(d[:7] for d in per_day.elements())
print('articles per month:', dict(sorted(by_month.items())))
outlets = Counter(a['outlet'] for a in articles)
print(f'{len(outlets)} outlets:', outlets.most_common())

edge_files = glob.glob(os.path.join(D, 'edges', '*.parquet'))
n_edges = sum(pq.ParquetFile(p).metadata.num_rows for p in edge_files)
print(f'edges: {len(edge_files)} day files, {n_edges} cross-outlet pairs >= {THRESHOLD_ZH}')
cluster_path = os.path.join(D, 'clusters.parquet')
cluster_of = dict(zip(*pq.read_table(cluster_path).to_pydict().values())) if os.path.exists(cluster_path) else {}
sizes = Counter(cluster_of.values())
print(f'clusters: {len(cluster_of)} articles in {len(sizes)} clusters; size distribution:',
      dict(sorted(Counter(min(s, 50) for s in sizes.values()).items())), '(50 = 50+)')
_, members = daily_totals(articles, cluster_of)
print('clusters by number of outlets:', dict(sorted(Counter(len({a['outlet'] for a in m}) for m in members.values()).items())))

print('\n=== 2. cross-outlet cosine on 20 random days (window 8 days): pairs at each threshold')
random.seed(0)
hist = Counter()
for d in random.sample(days, min(20, len(days))):
    for _, _, c in day_edges(os.path.join(D, 'days'), d, 0.6, cross_outlet=True):
        for t in (0.6, 0.65, 0.7, 0.75, 0.8, 0.85, 0.9):
            hist[t] += c >= t
print({t: hist[t] for t in sorted(hist)})

print(f'\n=== 3. storm tests, today: min_outlets {MIN_OUTLETS}, min_days {MIN_DAYS}, share {STORM_SHARE}, '
      f'min_peak_share {MIN_PEAK_SHARE}')
funnel = Counter()
found = storms(articles, cluster_of, funnel=funnel)
for test, n in sorted(funnel.items()):
    print(f'  {n:8d}  {test[2:]}')
print(f'  -> {len(found)} storms')
print('\nlooser settings (min_outlets, min_days, share, min_peak_share) -> storms:')
for mo in (5, 3, 2):
    for md in (7, 3, 1):
        for sh in (0.01, 0.003, 0.001):
            n = len(storms(articles, cluster_of, min_days=md, min_outlets=mo, share=sh, min_peak_share=0.3))
            print(f'  {mo} {md} {sh:<6} -> {n}')

print('\n=== 4. the 25 largest clusters')
print('  articles outlets days max_share max_outlets peak_share first       title')
for cid, arts in sorted(members.items(), key=lambda kv: -len(kv[1]))[:25]:
    p = profile(arts, per_day)
    print(f"  {p['articles']:8d} {p['outlets']:7d} {p['days']:4d} {p['storm_share']:9.2%} {p['storm_outlets']:11d} "
          f"{p['peak_share']:10.2f} {p['first']}  {titles.get(cid, '')[:50]}")
PY
