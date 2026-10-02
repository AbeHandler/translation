#!/usr/bin/env python
"""
Media storms in the English CC-NEWS coverage of AI (src/media_storms.py, after Litterer et al. 2023). Steps:
    -step by_day   a worker: each WARC's embeddings + dates -> $STORMS/days/<date>/<warc>.parquet
    -step edges    a worker: each day's similar pairs (cosine >= 0.9, within 8 days) -> $STORMS/edges/<date>.parquet
    -step cluster  connected components of all edges -> $STORMS/clusters.parquet {url, cluster}
    -step storms   storm clusters (>= 7 days, >= 5 outlets in storm mode) -> $STORMS/storms.jsonl + a summary
with $STORMS = data/interim/media_storms. by_day and edges are workers (many in parallel, .lock files, finished
files skipped), so rerunning after more WARCs are embedded and dated only does the new part. Note: a day's edges
are computed once; rerun with -redo-edges after adding WARCs whose articles fall on days already done.

Run as a module from the repo root:
    python -m scripts.media_storms -step by_day
    python -m scripts.media_storms -step edges
    python -m scripts.media_storms -step cluster
    python -m scripts.media_storms -step storms
"""
import argparse
import glob
import json
import os
from collections import Counter

import pyarrow as pa
import pyarrow.parquet as pq

from config.paths import CC_NEWS_EMBEDDINGS_DIR, CC_NEWS_PUBDATES_DIR, MEDIA_STORMS_DIR
from src.file_worker import process_files
from src.media_storms import THRESHOLD, clusters, day_edges, split_by_day, storms, write_edges
from src.warc_worker_cli import optional_int, setup_worker_process


def parse_args():
    parser = argparse.ArgumentParser(description='Media storms in the English CC-NEWS coverage of AI')
    parser.add_argument('-step', required=True, choices=('by_day', 'edges', 'cluster', 'storms'))
    parser.add_argument('-embeddings-dir', default=str(CC_NEWS_EMBEDDINGS_DIR))
    parser.add_argument('-dates-dir', default=str(CC_NEWS_PUBDATES_DIR))
    parser.add_argument('-out-dir', default=str(MEDIA_STORMS_DIR))
    parser.add_argument('-threshold', type=float, default=THRESHOLD)
    parser.add_argument('-redo-edges', action='store_true', help='edges: recompute days that already have edges')
    parser.add_argument('-max-files', type=optional_int, default=None, help='workers: stop after N (testing)')
    return parser.parse_args()


def by_day(args):
    """Worker over the WARCs that have both embeddings and dates; a marker file per WARC says it's split."""
    days_dir, done_dir = os.path.join(args.out_dir, 'days'), os.path.join(args.out_dir, 'by_day_done')
    os.makedirs(done_dir, exist_ok=True)
    paths = [p for p in sorted(glob.glob(os.path.join(args.embeddings_dir, '*.parquet')))
             if os.path.exists(os.path.join(args.dates_dir, os.path.basename(p)))]

    def split(path, marker):
        warc = os.path.basename(path).removesuffix('.parquet')
        counts = split_by_day(path, os.path.join(args.dates_dir, os.path.basename(path)), days_dir, warc)
        with open(marker, 'w') as f:
            json.dump(counts, f)
        return {'days': len(counts), 'articles': sum(counts.values())}
    process_files(paths, lambda p: os.path.join(done_dir, os.path.basename(p) + '.json'), split, args.max_files)


def edges(args):
    days_dir, edges_dir = os.path.join(args.out_dir, 'days'), os.path.join(args.out_dir, 'edges')
    os.makedirs(edges_dir, exist_ok=True)
    days = sorted(d for d in os.listdir(days_dir) if os.path.isdir(os.path.join(days_dir, d)))
    if args.redo_edges:
        for d in days:
            path = os.path.join(edges_dir, d + '.parquet')
            if os.path.exists(path):
                os.remove(path)

    def compute(day_path, out):
        found = day_edges(days_dir, os.path.basename(day_path), args.threshold)
        write_edges(found, out)
        return {'edges': len(found)}

    def out_path(day_path):
        return os.path.join(edges_dir, os.path.basename(day_path) + '.parquet')
    process_files([os.path.join(days_dir, d) for d in days], out_path, compute, args.max_files)


def cluster(args):
    paths = sorted(glob.glob(os.path.join(args.out_dir, 'edges', '*.parquet')))
    cluster_of = clusters(paths)
    out = os.path.join(args.out_dir, 'clusters.parquet')
    pq.write_table(pa.table({'url': list(cluster_of), 'cluster': list(cluster_of.values())}), out)
    sizes = Counter(cluster_of.values())
    print(f'{len(paths)} days of edges -> {len(cluster_of)} articles in {len(sizes)} clusters -> {out}')
    print('largest:', sizes.most_common(5))


def storm_step(args):
    days_dir = os.path.join(args.out_dir, 'days')
    cluster_of = dict(zip(*pq.read_table(os.path.join(args.out_dir, 'clusters.parquet')).to_pydict().values()))
    articles, titles, seen = [], {}, set()
    for path in glob.glob(os.path.join(days_dir, '*', '*.parquet')):
        date = os.path.basename(os.path.dirname(path))
        for row in pq.read_table(path, columns=['url', 'outlet', 'title']).to_pylist():
            if row['url'] not in seen:
                seen.add(row['url'])
                articles.append({'url': row['url'], 'outlet': row['outlet'], 'date': date})
                if row['url'] in cluster_of:
                    titles.setdefault(cluster_of[row['url']], row['title'])
    found = storms(articles, cluster_of)
    out = os.path.join(args.out_dir, 'storms.jsonl')
    with open(out, 'w', encoding='utf-8') as f:
        for s in found:
            f.write(json.dumps({**s, 'title': titles.get(s['cluster'], '')}, ensure_ascii=False) + '\n')
    print(f'{len(articles)} articles, {len(set(cluster_of.values()))} clusters -> {len(found)} storms -> {out}')
    for s in found[:20]:
        print(f"  {s['articles']:5d} articles {s['storm_outlets']:3d}/{s['outlets']:3d} outlets in storm mode "
              f"{s['first']}..{s['last']} peak {s['peak']}  {titles.get(s['cluster'], '')[:70]}")


def main():
    setup_worker_process()  # logging; SIGTERM (scancel, time limit) exits cleanly and releases the file's lock
    args = parse_args()
    {'by_day': by_day, 'edges': edges, 'cluster': cluster, 'storms': storm_step}[args.step](args)


if __name__ == '__main__':
    main()
