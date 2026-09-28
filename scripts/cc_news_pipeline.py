#!/usr/bin/env python
"""
The CC-NEWS pipeline for a date range, in steps (-step), each reading only the previous step's output
(src/cc_news.py has the details):
    html   WARCs -> data/interim/cc_html/<warc>.parquet   raw en/zh article HTML; the only step that reads WARCs
    links  cc_html/<warc>.parquet -> data/interim/cc_links/<warc>.jsonl   each article's body links
    match  cc_links -> data/processed/cc_link_matches.jsonl   links to the seeds in config/seed_patterns.txt,
           including URL-encoded redirect links. Refuses unless every WARC in the range has its links file
           (-partial to match what there is).

html and links are worker steps: scripts/go.sh submits many copies to SLURM, which share the work through
.lock/.done files. Every step skips work already done, so it is safe to stop and rerun; a new seed pattern
only needs -step match. Clean slate: sbatch --export=NONE scripts/slurm/flush_cc_news.slurm

Run as a module from the repo root, so `src` and `config` import:
    python -m scripts.cc_news_pipeline -step html -start-date 20260901 -end-date 20260923
    python -m scripts.cc_news_pipeline -step links -start-date 20260901 -end-date 20260923
    python -m scripts.cc_news_pipeline -step match -start-date 20260901 -end-date 20260923
    python -m scripts.cc_news_pipeline -step html -start-date 20260923 -end-date 20260923 -max-warcs 1 -max-n 100
"""
import argparse
import os

from config.paths import (CC_HTML_DIR, CC_LINK_MATCHES_PATH, CC_LINKS_DIR, SEED_PATTERNS_PATH,
                          extract_warc_html_work_dir, warc_cache_dir)
from src.cc_news import (ArticleHtmlArchiver, ArticleLinkExtractor, CCNewsIndex, HtmlArchivePipeline, WarcWorker,
                         WorkDir, match_seed_links, read_patterns, warc_files, warc_name, with_max_n)
from src.file_worker import process_files
from src.warc_worker_cli import add_warc_worker_args, setup_worker_process

STEPS = ('html', 'links', 'match')


def parse_args():
    parser = argparse.ArgumentParser(description='The CC-NEWS pipeline: html, links, match')
    parser.add_argument('-step', required=True, choices=STEPS)
    add_warc_worker_args(parser, default_work_dir_help='html step; default $TMP/extract_warc_html')
    parser.add_argument('-html-dir', default=str(CC_HTML_DIR))
    parser.add_argument('-links-dir', default=str(CC_LINKS_DIR))
    parser.add_argument('-patterns', default=str(SEED_PATTERNS_PATH), help='one substring per line')
    parser.add_argument('-matches-path', default='', help=f'default {CC_LINK_MATCHES_PATH}')
    parser.add_argument('-partial', action='store_true', help='match: even if some WARCs have no links yet')
    return parser.parse_args()


def index(args):
    return CCNewsIndex(args.warc_cache_dir or str(warc_cache_dir()), args.aws)


def html(args):
    worker = WarcWorker(index=index(args), work_dir=WorkDir(args.work_dir or str(extract_warc_html_work_dir()),
                                                            args.max_n),
                        max_warcs=args.max_warcs)
    HtmlArchivePipeline(worker, ArticleHtmlArchiver(max_n=args.max_n), args.html_dir).run(args.start_date,
                                                                                          args.end_date)


def links(args):
    html_paths = warc_files(args.html_dir, '.parquet', args.start_date, args.end_date, args.max_n)
    if not html_paths:
        raise FileNotFoundError(f'no HTML Parquet files for {args.start_date}..{args.end_date} in {args.html_dir}; '
                                'run -step html first')

    def links_path(html_path):
        return os.path.join(args.links_dir, os.path.basename(html_path).removesuffix('.parquet') + '.jsonl')
    n_done = process_files(html_paths, links_path, ArticleLinkExtractor().write, max_files=args.max_warcs)
    print(f'this worker wrote {n_done} links files; '
          f'{sum(os.path.exists(links_path(p)) for p in html_paths)} of {len(html_paths)} HTML files have links')


def match(args):
    keys = index(args).list_warcs(args.start_date, args.end_date)
    patterns = read_patterns(args.patterns)
    matches_path = args.matches_path or with_max_n(str(CC_LINK_MATCHES_PATH), args.max_n)

    def links_path(key):
        return os.path.join(args.links_dir, with_max_n(warc_name(key), args.max_n) + '.jsonl')
    counts = match_seed_links(keys, links_path, patterns, matches_path, partial=args.partial)
    print(f'{len(keys)} WARCs, {args.start_date}..{args.end_date} -> {matches_path}')
    for pattern in patterns:
        print(f'  {counts[pattern]:6d}  {pattern}')
    print('\nSpot checks:')
    print(f'  jq -r .pattern {matches_path} | sort | uniq -c')
    print(f"  jq -c '{{href, decoded, url, language}}' {matches_path} | head")


def main():
    setup_worker_process()
    args = parse_args()
    {'html': html, 'links': links, 'match': match}[args.step](args)


if __name__ == '__main__':
    main()
