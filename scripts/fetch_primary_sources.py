#!/usr/bin/env python
"""
A worker: fetch the raw text of every URL on the primary-source store's to-do list (data/interim/primary/todo.tsv;
scripts/add_primary_todo.py adds to it) into data/interim/primary/<sha1 of the URL's key>.json {key, url, final_url,
status, content_type, title, text, n_chars, fetched_at} (src/source_texts.py). URLs in random order; each is
fetched once across all workers (.lock files, src/file_worker.py), and one that has its file is skipped, so rerun or
add workers any time, and after the list grows. A failed fetch writes a file with status 0 and the error;
-retry-failed fetches those again. When done, the worker rebuilds data/processed/primary.pq from the store
(src/source_texts.py compile_store).

Run as a module from the repo root:
    python -m scripts.fetch_primary_sources
    python -m scripts.fetch_primary_sources -max-files 5         # test
"""
import argparse
import glob
import json
import os

from config.paths import PRIMARY_DB_PATH, PRIMARY_TEXTS_DIR
from src.file_worker import process_files
from src.source_texts import SourceFetcher, compile_store, read_todo, source_path, store_source
from src.warc_worker_cli import optional_int, setup_worker_process


def parse_args():
    parser = argparse.ArgumentParser(description='Fetch the raw text of the primary sources')
    parser.add_argument('-store-dir', default=str(PRIMARY_TEXTS_DIR), help='todo.tsv in, <sha1>.json out')
    parser.add_argument('-db', default=str(PRIMARY_DB_PATH), help='rebuilt from the store when the worker is done')
    parser.add_argument('-retry-failed', action='store_true', help='first delete the files of failed fetches')
    parser.add_argument('-max-files', type=optional_int, default=None, help='stop after N (testing)')
    return parser.parse_args()


def retry_failed(out_dir):
    for path in glob.glob(os.path.join(out_dir, '*.json')):
        with open(path, encoding='utf-8') as f:
            if json.load(f)['status'] != 200:
                os.remove(path)


def main():
    setup_worker_process()
    args = parse_args()
    os.makedirs(args.store_dir, exist_ok=True)
    if args.retry_failed:
        retry_failed(args.store_dir)
    todo = read_todo(os.path.join(args.store_dir, 'todo.tsv'))
    if not todo:
        raise FileNotFoundError(f'nothing on {args.store_dir}/todo.tsv: add URLs with scripts/add_primary_todo.py')
    fetcher = SourceFetcher()

    def fetch(key, out_path):
        row = store_source(fetcher, todo[key], args.store_dir)
        return {'status': row['status'], 'chars': row['n_chars']}
    process_files(list(todo), lambda key: source_path(args.store_dir, todo[key]), fetch, args.max_files)
    rows = compile_store(args.store_dir, args.db)   # keep the table current: the last worker to finish leaves it whole
    print(f'{len(rows)} sources in {args.db}', flush=True)


if __name__ == '__main__':
    main()
