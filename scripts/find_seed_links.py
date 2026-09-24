#!/usr/bin/env python
"""
Driver: find which CC-NEWS articles link to the seed URLs in config/seed_patterns.txt.

Builds a SeedLinkPipeline (src/cc_news.py) from the command line and config/paths.py and runs
every step for the date range. scripts/go.sh submits many copies of this to SLURM; they share
the work through the .lock/.done files in -work-dir. scripts/flush.sh deletes everything this
writes, for a clean rerun.

Run as a module from the repo root, so `src` and `config` import:
    python -m scripts.find_seed_links -start-date 20260901 -end-date 20260923
    python -m scripts.find_seed_links -start-date 20260923 -end-date 20260923 -max-warcs 1 -max-n 100
"""
import argparse

from config.paths import CC_LINK_MATCHES_PATH, CC_LINKS_DIR, SEED_PATTERNS_PATH, find_seed_links_work_dir
from src.cc_news import (ArticleLinkExtractor, CCNewsIndex, SeedLinkPipeline, WarcWorker, WorkDir,
                         read_patterns, with_max_n)
from src.warc_worker_cli import add_warc_worker_args, setup_worker_process


def parse_args():
    parser = argparse.ArgumentParser(description='Find which CC-NEWS articles link to a set of seed URLs')
    add_warc_worker_args(parser, default_work_dir_help='default $TMP/find_seed_links')
    parser.add_argument('-output-dir', default='', help=f'links jsonl files (default {CC_LINKS_DIR})')
    parser.add_argument('-patterns', default=str(SEED_PATTERNS_PATH), help='one substring per line')
    parser.add_argument('-matches-path', default='', help=f'default {CC_LINK_MATCHES_PATH}')
    return parser.parse_args()


def main():
    setup_worker_process()
    args = parse_args()
    worker = WarcWorker(
        index=CCNewsIndex(args.aws),
        work_dir=WorkDir(args.work_dir or str(find_seed_links_work_dir()), args.max_n),
        max_warcs=args.max_warcs,
    )
    pipeline = SeedLinkPipeline(
        worker=worker,
        extractor=ArticleLinkExtractor(max_n=args.max_n),
        output_dir=args.output_dir or str(CC_LINKS_DIR),
        patterns=read_patterns(args.patterns),
        matches_path=args.matches_path or with_max_n(str(CC_LINK_MATCHES_PATH), args.max_n),
    )
    pipeline.run(args.start_date, args.end_date)


if __name__ == '__main__':
    main()
