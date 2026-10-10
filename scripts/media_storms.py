#!/usr/bin/env python
"""
Media storms in news coverage of AI (src/media_storms.py, after Litterer et al. 2023), in one of two corpora:
    -corpus en   the English CC-NEWS articles (default) -> $STORMS = data/interim/media_storms
    -corpus zh   the Chinese site crawls (their bge-base-zh embeddings, scripts/embed_site_crawls.py)
                 -> $STORMS = data/interim/media_storms_zh
Steps:
    -step by_day   a worker: each WARC's embeddings + dates -> $STORMS/days/<date>/<warc>.parquet
                   (zh: each crawled HTML file's Chinese AI pages, dated from their HTML, + their embeddings
                   -> $STORMS/days/<date>/<domain>__<part>.parquet, and their links -> $STORMS/links/)
    -step edges    a worker: each day's similar pairs (cosine >= 0.9, within 8 days) -> $STORMS/edges/<date>.parquet
    -step cluster  connected components of all edges -> $STORMS/clusters.parquet {url, cluster}
    -step storms   storm clusters (>= 7 days, in storm mode: >= 1% of all AI articles over 3 days from >= 5 outlets,
                   a burst around the peak)
                   -> $STORMS/storms.jsonl + a summary
    -step seeds    the documents each storm's articles cite (cc_links) -> $STORMS/storm_seeds.jsonl
by_day and edges are workers (many in parallel, .lock files, finished
files skipped), so rerunning after more WARCs are embedded and dated only does the new part. A day whose articles
(or one of the next WINDOW_DAYS days) changed since its edges were computed is redone; -redo-edges redoes all.

Run as a module from the repo root:
    python -m scripts.media_storms -step by_day
    python -m scripts.media_storms -step edges
    python -m scripts.media_storms -step cluster
    python -m scripts.media_storms -step storms
    python -m scripts.media_storms -step seeds
    python -m scripts.media_storms -corpus zh -step by_day
"""
import argparse
import contextlib
import glob
import json
import os
from collections import Counter, defaultdict

import pyarrow as pa
import pyarrow.parquet as pq

import datetime

from config.paths import (CC_LINKS_DIR, CC_NEWS_EMBEDDINGS_DIR, CC_NEWS_PUBDATES_DIR, MEDIA_STORMS_DIR,
                          MEDIA_STORMS_ZH_DIR, SITE_CRAWLS_DIR)
from src.file_worker import process_files
from src.external_links import external_links
from src.media_storms import (MIN_DAYS, MIN_DAYS_ZH, MIN_OUTLETS, MIN_OUTLETS_ZH, MIN_PEAK_SHARE, STORM_SHARE,
                              STORM_WINDOW, THRESHOLD, THRESHOLD_ZH, WINDOW_DAYS, clusters, daily_totals, day_edges,
                              outlet_of, profile, shift, split_by_day, split_site_crawl_by_day, storm_seeds, storms,
                              write_edges)
from src.warc_worker_cli import optional_int, setup_worker_process


def parse_args():
    parser = argparse.ArgumentParser(description='Media storms in the English CC-NEWS coverage of AI')
    parser.add_argument('-step', required=True, choices=('by_day', 'edges', 'cluster', 'storms', 'seeds'))
    parser.add_argument('-corpus', default='en', choices=('en', 'zh'))
    parser.add_argument('-embeddings-dir', default=str(CC_NEWS_EMBEDDINGS_DIR), help='en')
    parser.add_argument('-dates-dir', default=str(CC_NEWS_PUBDATES_DIR), help='en')
    parser.add_argument('-crawls-dir', default=str(SITE_CRAWLS_DIR), help='zh: <domain>/html, <domain>/embeddings')
    parser.add_argument('-out-dir', default=None, help='default: by corpus')
    parser.add_argument('-links-dir', default=None, help="seeds: the articles' links (default: by corpus)")
    parser.add_argument('-threshold', type=float, default=None, help=f'default {THRESHOLD} (en), {THRESHOLD_ZH} (zh)')
    parser.add_argument('-redo-edges', action='store_true',
                        help='edges: recompute days that already have edges (one process only; with many '
                             'workers, REDO_EDGES=1 in go_media_storms.sh deletes them once first)')
    parser.add_argument('-min-days', type=int, default=None,
                        help=f'storms; default {MIN_DAYS} (en), {MIN_DAYS_ZH} (zh)')
    parser.add_argument('-min-outlets', type=int, default=None,
                        help=f'storms; default {MIN_OUTLETS} (en), {MIN_OUTLETS_ZH} (zh)')
    parser.add_argument('-storm-share', type=float, default=STORM_SHARE,
                        help="storms: the story's share of all AI articles over the window, for storm mode")
    parser.add_argument('-min-peak-share', type=float, default=MIN_PEAK_SHARE, help='storms')
    parser.add_argument('-max-files', type=optional_int, default=None, help='workers: stop after N (testing)')
    args = parser.parse_args()
    zh = args.corpus == 'zh'
    args.threshold = args.threshold or (THRESHOLD_ZH if zh else THRESHOLD)
    args.min_days = args.min_days or (MIN_DAYS_ZH if zh else MIN_DAYS)
    args.min_outlets = args.min_outlets or (MIN_OUTLETS_ZH if zh else MIN_OUTLETS)
    args.out_dir = args.out_dir or str(MEDIA_STORMS_ZH_DIR if zh else MEDIA_STORMS_DIR)
    args.links_dir = args.links_dir or (os.path.join(args.out_dir, 'links') if zh else str(CC_LINKS_DIR))
    return args


def by_day(args):
    (by_day_zh if args.corpus == 'zh' else by_day_en)(args)


def by_day_zh(args):
    """Worker over the crawled HTML files that have embeddings; a marker file per HTML file says it's split. A file
    whose HTML or embeddings changed since its marker is split again (pages embedded after the split were skipped as
    "no embedding": the gold lists showed 78 of 82 crawled, embedded incident articles missing from the day files);
    its day files are overwritten, so nothing is counted twice."""
    days_dir, done_dir = os.path.join(args.out_dir, 'days'), os.path.join(args.out_dir, 'by_day_done')
    os.makedirs(done_dir, exist_ok=True)
    os.makedirs(args.links_dir, exist_ok=True)
    last_day = datetime.date.today().isoformat()

    def key_of(path):   # <domain>__<part>
        return os.path.basename(os.path.dirname(os.path.dirname(path))) + '__' + \
            os.path.basename(path).removesuffix('.parquet')

    def embeddings_of(path):
        return os.path.join(os.path.dirname(os.path.dirname(path)), 'embeddings', os.path.basename(path))

    paths = [p for p in sorted(glob.glob(os.path.join(args.crawls_dir, '*', 'html', '*.parquet')))
             if os.path.exists(embeddings_of(p))]
    stale = 0
    for p in paths:     # split before its pages were (all) embedded: its later-embedded pages never got in. Redo it
        marker = os.path.join(done_dir, key_of(p) + '.json')
        with contextlib.suppress(FileNotFoundError):    # many workers check at once: another may remove it first
            if os.path.exists(marker) and max(os.path.getmtime(p), os.path.getmtime(embeddings_of(p))) > \
                    os.path.getmtime(marker):
                os.remove(marker)
                stale += 1
    if stale:
        print(f'{stale} crawl files split before their HTML or embeddings last changed: split again', flush=True)

    def split(path, marker):
        key = key_of(path)
        counts, funnel = split_site_crawl_by_day(path, embeddings_of(path), days_dir,
                                                 os.path.join(args.links_dir, key + '.jsonl'), key, last_day)
        with open(marker, 'w') as f:
            json.dump({'days': counts, 'pages': funnel}, f)
        return {'days': len(counts), 'articles': sum(counts.values()), 'pages': funnel}
    process_files(paths, lambda p: os.path.join(done_dir, key_of(p) + '.json'), split, args.max_files)


def by_day_en(args):
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


def stale(days_dir, day, edges_path):
    """True if an article file of the day, or of the following days its edges reach (WINDOW_DAYS), is newer than
    its edges file."""
    edges_time = os.path.getmtime(edges_path)
    for k in range(WINDOW_DAYS):
        folder = os.path.join(days_dir, shift(day, k))
        if os.path.isdir(folder) and any(os.path.getmtime(os.path.join(folder, name)) > edges_time
                                         for name in os.listdir(folder)):
            return True
    return False


def edges(args):
    days_dir, edges_dir = os.path.join(args.out_dir, 'days'), os.path.join(args.out_dir, 'edges')
    os.makedirs(edges_dir, exist_ok=True)
    if not os.path.isdir(days_dir):
        raise FileNotFoundError(f'{days_dir} does not exist: the by_day step wrote no articles; check its logs '
                                '(logs/scripts/slurm/media_storms_*.out with "by_day" in the to-do lines)')
    days = sorted(d for d in os.listdir(days_dir) if os.path.isdir(os.path.join(days_dir, d)))
    for d in days:   # a day whose edges' articles changed since (new WARCs or crawl files) is redone
        path = os.path.join(edges_dir, d + '.parquet')
        with contextlib.suppress(FileNotFoundError):    # many workers check at once: another may remove it first
            if os.path.exists(path) and (args.redo_edges or stale(days_dir, d, path)):
                os.remove(path)

    def compute(day_path, out):
        found = day_edges(days_dir, os.path.basename(day_path), args.threshold, cross_outlet=args.corpus == 'zh')
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
                articles.append({'url': row['url'], 'outlet': outlet_of(row['outlet']), 'date': date})
                if row['url'] in cluster_of:
                    titles.setdefault(cluster_of[row['url']], row['title'])
    funnel = Counter()
    found = storms(articles, cluster_of, min_days=args.min_days, min_outlets=args.min_outlets,
                   share=args.storm_share, min_peak_share=args.min_peak_share, funnel=funnel)
    out = os.path.join(args.out_dir, 'storms.jsonl')
    with open(out, 'w', encoding='utf-8') as f:
        for s in found:
            f.write(json.dumps({**s, 'title': titles.get(s['cluster'], '')}, ensure_ascii=False) + '\n')
    print(f'{len(articles)} articles, {len(set(cluster_of.values()))} clusters -> {len(found)} storms -> {out}')
    for s in found[:20]:
        print(f"  {s['articles']:5d} articles, {s['outlets']:4d} outlets, up to {s['storm_share']:.1%} of all AI "
              f"articles, {s['first']}..{s['last']} peak {s['peak']}  {titles.get(s['cluster'], '')[:60]}")
    print('\nclusters passing each test in turn:')
    for test, n in sorted(funnel.items()):
        print(f'  {n:8d}  {test[2:]}')
    per_day, members = daily_totals(articles, cluster_of)
    print('\nthe 20 largest clusters (storm or not):')
    print('  articles outlets max_share max_outlets storm_days days peak_share  title')
    for cid, arts in sorted(members.items(), key=lambda kv: -len(kv[1]))[:20]:
        p = profile(arts, per_day, STORM_WINDOW, args.storm_share, args.min_outlets)
        print(f"  {p['articles']:8d} {p['outlets']:7d} {p['storm_share']:9.2%} {p['storm_outlets']:11d} "
              f"{p['storm_days']:10d} {p['days']:4d} {p['peak_share']:10.2f}  {p['first']}  {titles.get(cid, '')[:50]}")
    print(f'\nAI articles per day in the corpus: median {sorted(per_day.values())[len(per_day) // 2]}, '
          f'so storm mode needs about {args.storm_share * 3 * sorted(per_day.values())[len(per_day) // 2]:.0f} '
          f'of a story\'s articles in {STORM_WINDOW} days')


def article_url(line):
    """The article URL of a links-file line without parsing the JSON (each line starts {"url": "...")."""
    start = line.find('"url": "') + 8
    return line[start:line.find('"', start)]


def seed_step(args):
    with open(os.path.join(args.out_dir, 'storms.jsonl'), encoding='utf-8') as f:
        wanted = {json.loads(line)['cluster'] for line in f}
    clusters_ = pq.read_table(os.path.join(args.out_dir, 'clusters.parquet')).to_pydict()
    cluster_of = {u: c for u, c in zip(clusters_['url'], clusters_['cluster']) if c in wanted}
    members, urls_of_warc = defaultdict(set), defaultdict(set)
    for path in glob.glob(os.path.join(args.out_dir, 'days', '*', '*.parquet')):
        warc = os.path.basename(path).removesuffix('.parquet')
        for url in pq.read_table(path, columns=['url']).column('url').to_pylist():
            if url in cluster_of:
                members[cluster_of[url]].add(url)
                urls_of_warc[warc].add(url)
    print(f'{len(wanted)} storms, {len(cluster_of)} articles in {len(urls_of_warc)} WARCs; reading their links',
          flush=True)
    links_of, missing = {}, 0
    for n, (warc, urls) in enumerate(urls_of_warc.items(), 1):
        path = os.path.join(args.links_dir, warc + '.jsonl')
        if not os.path.exists(path):
            missing += 1
            continue
        with open(path, encoding='utf-8') as f:
            for line in f:
                if article_url(line) in urls:
                    article = json.loads(line)
                    hrefs = (link['href'] for link in article['links'])
                    links_of[article['url']] = external_links(article['url'], hrefs)
        if n % 500 == 0:
            print(f'  {n}/{len(urls_of_warc)} links files read', flush=True)
    if missing:
        raise FileNotFoundError(f'{missing} of {len(urls_of_warc)} WARCs have no links file in {args.links_dir}')
    found = storm_seeds({c: sorted(u) for c, u in members.items()}, links_of)
    out = os.path.join(args.out_dir, 'storm_seeds.jsonl')
    with open(out + '.part', 'w', encoding='utf-8') as f:
        for cid, row in found.items():
            f.write(json.dumps({'cluster': cid, **row}, ensure_ascii=False) + '\n')
    os.rename(out + '.part', out)
    focused = sorted(found.items(), key=lambda kv: -kv[1]['seed_share'])
    print(f'{len(found)} storms -> {out}; {sum(r["seed_share"] > 0 for r in found.values())} with a seed document')
    for cid, row in focused[:20]:
        if not row['seeds']:            # no cited document left once page assets and homepages are dropped
            continue
        print(f"  {row['seed_share']:.2f} of {len(members[cid]):5d} articles cite {row['seeds'][0]['href'][:100]}")


def main():
    setup_worker_process()  # logging; SIGTERM (scancel, time limit) exits cleanly and releases the file's lock
    args = parse_args()
    {'by_day': by_day, 'edges': edges, 'cluster': cluster, 'storms': storm_step, 'seeds': seed_step}[args.step](args)


if __name__ == '__main__':
    main()
