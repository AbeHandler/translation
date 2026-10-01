#!/usr/bin/env python
"""
The regular Common Crawl since -since-year, streamed once, keeping English pages that say "AI"
(src/common_crawl_full), in $TMP/cc_full/:
    -step list    every WARC path of every crawl since then -> warc_paths.txt (skipped if it exists)
    -step filter  a worker: WARCs from warc_paths.txt in random order -> <warc>.ai.warc.gz, skipping WARCs done
                  or claimed by another worker. Start many (scripts/go_cc_full.sh).
    -step all     list, then filter (the one-worker version)
    -step links   a worker: each <warc>.ai.warc.gz without links yet -> <warc>.links.jsonl (the pages' body links)
    -step queue   each links file without a queue shard -> $TMP/cc_full_queue/shard_<warc>.jsonl (its external
                  links); process them with: bash scripts/process_queue.sh cc_full
    -step cleanup empties every <warc>.ai.warc.gz that has its links file, to save space. The empty file still
                  marks the WARC done for every filter worker, so it is never streamed again. The links are kept.

Run as a module from the repo root:
    python -m scripts.cc_full -step list
    python -m scripts.cc_full -step filter -max-warcs 1      # test: one WARC
    python -m scripts.cc_full -step links
    python -m scripts.cc_full -step queue
    python -m scripts.cc_full -step cleanup
"""
import argparse
import glob
import logging
import os

from config.paths import cc_full_dir, cc_full_queue_dir
from src.common_crawl_full.filter import filter_warc
from src.common_crawl_full.index import write_warc_list
from src.common_crawl_full.links import delete_linked_warcs, page_links, queue_shards
from src.common_crawl_full.worker import links_path, process_warcs
from src.file_worker import process_files
from src.warc_worker_cli import optional_int, setup_worker_process


def parse_args():
    parser = argparse.ArgumentParser(description='English pages saying AI from the regular Common Crawl')
    parser.add_argument('-step', required=True, choices=('list', 'filter', 'all', 'links', 'queue', 'cleanup'))
    parser.add_argument('-since-year', type=int, default=2023)
    parser.add_argument('-out-dir', default='', help='default $TMP/cc_full')
    parser.add_argument('-max-warcs', type=optional_int, default=None, help='filter, links: stop after N (testing)')
    parser.add_argument('-queue-dir', default='', help='default $TMP/cc_full_queue')
    return parser.parse_args()


def main():
    setup_worker_process()  # logging; SIGTERM (scancel, time limit) exits cleanly and releases the WARC's lock
    logging.getLogger('langdetect').setLevel(logging.WARNING)
    args = parse_args()
    out_dir = args.out_dir or str(cc_full_dir())
    list_path = os.path.join(out_dir, 'warc_paths.txt')
    if args.step in ('list', 'all'):
        print(f'{write_warc_list(list_path, args.since_year)} WARCs since {args.since_year} in {list_path}')
    if args.step in ('filter', 'all'):
        if not os.path.exists(list_path):
            raise FileNotFoundError(f'no {list_path}; run -step list first')
        n_done = process_warcs(list_path, out_dir, filter_warc, args.max_warcs)
        names = os.listdir(out_dir)
        n_files = len({n.removesuffix('.ai.warc.gz').removesuffix('.links.jsonl') for n in names
                       if n.endswith(('.ai.warc.gz', '.links.jsonl'))})
        print(f'this worker did {n_done} WARCs; {n_files} done in all -> {out_dir}')
    if args.step == 'links':
        ai_warcs = sorted(glob.glob(os.path.join(out_dir, '*.ai.warc.gz')))
        n_done = process_files(ai_warcs, links_path, page_links, max_files=args.max_warcs)
        n_links = len(glob.glob(os.path.join(out_dir, '*.links.jsonl')))
        print(f'this worker did {n_done}; {n_links} WARCs have links ({len(ai_warcs)} AI WARCs on disk)')
    if args.step == 'queue':
        queue_dir = args.queue_dir or str(cc_full_queue_dir())
        n_shards, n_rows = queue_shards(out_dir, queue_dir)
        print(f'{n_shards} new shards ({n_rows} external links) in {queue_dir}')
        print('Process them: bash scripts/process_queue.sh cc_full')
    if args.step == 'cleanup':
        n, freed = delete_linked_warcs(out_dir)
        print(f'emptied {n} AI WARCs that have links files ({freed / 1e9:.1f} GB freed) in {out_dir}')


if __name__ == '__main__':
    main()
