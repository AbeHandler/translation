#!/usr/bin/env python
"""
Driver: save the raw HTML of every English/Chinese article in the CC-NEWS WARCs for a date range,
one zstd-compressed Parquet file per WARC (columns: url, language, warc_date, content_type,
record_id, html), for parsing later into text, title, date, etc.

Builds an HtmlArchivePipeline (src/cc_news.py). scripts/go.sh submits many copies of this to
SLURM; they share the work through the .lock/.done files in -work-dir, which is separate from
find_seed_links', so the two never block or skip each other. scripts/flush.sh deletes what this writes.

Run as a module from the repo root, so `src` and `config` import:
    python -m scripts.extract_warc_html -start-date 20260901 -end-date 20260923
    python -m scripts.extract_warc_html -start-date 20260923 -end-date 20260923 -max-warcs 1 -max-n 100

Read the result with e.g. duckdb:
    SELECT language, count(*) FROM 'data/interim/cc_html/*.parquet' GROUP BY 1
"""
import argparse

from config.paths import CC_HTML_DIR, extract_warc_html_work_dir, warc_cache_dir
from src.cc_news import ArticleHtmlArchiver, CCNewsIndex, HtmlArchivePipeline, WarcWorker, WorkDir
from src.warc_worker_cli import add_warc_worker_args, setup_worker_process


def parse_args():
    parser = argparse.ArgumentParser(description='Save raw en/zh article HTML from CC-NEWS WARCs as Parquet')
    add_warc_worker_args(parser, default_work_dir_help='default $TMP/extract_warc_html')
    parser.add_argument('-output-dir', default='', help=f'Parquet files (default {CC_HTML_DIR})')
    return parser.parse_args()


def main():
    setup_worker_process()
    args = parse_args()
    worker = WarcWorker(
        index=CCNewsIndex(args.warc_cache_dir or str(warc_cache_dir()), args.aws),
        work_dir=WorkDir(args.work_dir or str(extract_warc_html_work_dir()), args.max_n),
        max_warcs=args.max_warcs,
    )
    pipeline = HtmlArchivePipeline(
        worker=worker,
        archiver=ArticleHtmlArchiver(max_n=args.max_n),
        output_dir=args.output_dir or str(CC_HTML_DIR),
    )
    pipeline.run(args.start_date, args.end_date)


if __name__ == '__main__':
    main()
