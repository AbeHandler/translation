#!/usr/bin/env python
"""
A worker: publication dates (src/news_pubdates.py) of the embedded English CC-NEWS articles about AI:
    data/interim/cc_news_embeddings/<warc>.parquet (+ cc_html/<warc>.parquet)
        -> data/interim/cc_news_pubdates/<warc>.parquet
WARCs in random order, each done once across workers (.lock files), WARCs with a dates file skipped.
scripts/date_cc_news.sh submits many workers.

Run as a module from the repo root:
    python -m scripts.date_cc_news
    python -m scripts.date_cc_news -max-files 1        # test: one WARC
"""
import argparse
import glob
import os
import warnings

from config.paths import CC_HTML_DIR, CC_NEWS_EMBEDDINGS_DIR, CC_NEWS_PUBDATES_DIR
from src.file_worker import process_files
from src.news_pubdates import date_file
from src.warc_worker_cli import optional_int, setup_worker_process


def parse_args():
    parser = argparse.ArgumentParser(description='Publication dates of the embedded English CC-NEWS articles')
    parser.add_argument('-embeddings-dir', default=str(CC_NEWS_EMBEDDINGS_DIR))
    parser.add_argument('-html-dir', default=str(CC_HTML_DIR))
    parser.add_argument('-out-dir', default=str(CC_NEWS_PUBDATES_DIR))
    parser.add_argument('-max-files', type=optional_int, default=None, help='stop after N WARCs (testing)')
    return parser.parse_args()


def main():
    setup_worker_process()  # logging; SIGTERM (scancel, time limit) exits cleanly and releases the WARC's lock
    warnings.filterwarnings('ignore', message='tzname .* identified but not understood')  # EDT, IST: day kept
    args = parse_args()
    paths = sorted(glob.glob(os.path.join(args.embeddings_dir, '*.parquet')))
    os.makedirs(args.out_dir, exist_ok=True)

    def out_path(path):
        return os.path.join(args.out_dir, os.path.basename(path))
    n_done = process_files(paths, out_path, lambda path, out: date_file(path, args.html_dir, out), args.max_files)
    n_out = len(glob.glob(os.path.join(args.out_dir, '*.parquet')))
    print(f'this worker dated {n_done} WARCs; {n_out} of {len(paths)} have dates in {args.out_dir}')


if __name__ == '__main__':
    main()
