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
import datetime
import logging

from config.paths import CC_LINK_MATCHES_PATH, CC_LINKS_DIR, SEED_PATTERNS_PATH, find_seed_links_work_dir
from src.cc_news import (ArticleLinkExtractor, CCNewsIndex, SeedLinkPipeline, WorkDir, read_patterns,
                         with_max_n)


def parse_args():
    """SLURM passes unset optional values as '', so every optional flag treats '' as its default."""
    parser = argparse.ArgumentParser(description='Find which CC-NEWS articles link to a set of seed URLs')
    parser.add_argument('-start-date', required=True, type=parse_date, help='YYYYMMDD, inclusive')
    parser.add_argument('-end-date', required=True, type=parse_date, help='YYYYMMDD, inclusive')
    parser.add_argument('-aws', default='aws', help='path to the aws CLI')
    parser.add_argument('-work-dir', default='', help='downloads and .lock/.done files (default $TMP/find_seed_links)')
    parser.add_argument('-output-dir', default='', help=f'links jsonl files (default {CC_LINKS_DIR})')
    parser.add_argument('-patterns', default=str(SEED_PATTERNS_PATH), help='one substring per line')
    parser.add_argument('-matches-path', default='', help=f'default {CC_LINK_MATCHES_PATH}')
    parser.add_argument('-max-n', type=optional_int, default=None, help='stop after N rows per WARC (testing)')
    parser.add_argument('-max-warcs', type=optional_int, default=None, help='stop after N WARCs (testing)')
    return parser.parse_args()


def parse_date(text):
    return datetime.datetime.strptime(text, '%Y%m%d').date()


def optional_int(text):
    return int(text) if text else None


def main():
    args = parse_args()
    logging.basicConfig(level=logging.INFO)
    logging.getLogger('readability').setLevel(logging.ERROR)  # noisy on malformed pages
    pipeline = SeedLinkPipeline(
        index=CCNewsIndex(args.aws),
        extractor=ArticleLinkExtractor(max_n=args.max_n),
        work_dir=WorkDir(args.work_dir or str(find_seed_links_work_dir()), args.max_n),
        output_dir=args.output_dir or str(CC_LINKS_DIR),
        patterns=read_patterns(args.patterns),
        matches_path=args.matches_path or with_max_n(str(CC_LINK_MATCHES_PATH), args.max_n),
        max_warcs=args.max_warcs,
    )
    pipeline.run(args.start_date, args.end_date)


if __name__ == '__main__':
    main()
