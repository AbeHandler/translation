#!/usr/bin/env python
"""
The regular Common Crawl since -since-year, streamed once, keeping English pages that say "AI"
(src/common_crawl_full), in $TMP/cc_full/:
    -step list    every WARC path of every crawl since then -> warc_paths.txt (skipped if it exists)
    -step filter  a worker: WARCs from warc_paths.txt in random order -> <warc>.ai.warc.gz, skipping WARCs done
                  or claimed by another worker. Start many (scripts/go_cc_full.sh).
    -step all     list, then filter (the one-worker version)

Run as a module from the repo root:
    python -m scripts.cc_full -step list
    python -m scripts.cc_full -step filter -max-warcs 1      # test: one WARC
"""
import argparse
import logging
import os

from config.paths import cc_full_dir
from src.common_crawl_full.filter import filter_warc
from src.common_crawl_full.index import write_warc_list
from src.common_crawl_full.worker import process_warcs
from src.warc_worker_cli import optional_int, setup_worker_process


def parse_args():
    parser = argparse.ArgumentParser(description='English pages saying AI from the regular Common Crawl')
    parser.add_argument('-step', required=True, choices=('list', 'filter', 'all'))
    parser.add_argument('-since-year', type=int, default=2023)
    parser.add_argument('-out-dir', default='', help='default $TMP/cc_full')
    parser.add_argument('-max-warcs', type=optional_int, default=None, help='filter: stop after N WARCs (testing)')
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
        n_files = sum(name.endswith('.ai.warc.gz') for name in os.listdir(out_dir))
        print(f'this worker did {n_done} WARCs; {n_files} done in all -> {out_dir}')


if __name__ == '__main__':
    main()
