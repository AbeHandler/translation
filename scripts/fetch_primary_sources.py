#!/usr/bin/env python
"""
A worker: fetch the raw text of every primary source (data/processed/primary_sources.tsv, src/primary_sources.py)
into data/interim/primary/<sha1 of its document key>.json {document, url, final_url, status, content_type, title,
text, n_chars, fetched_at} (src/source_texts.py). Sources in random order; each is fetched once across all workers
(.lock files, src/file_worker.py), and one that has its file is skipped, so rerun or add workers any time, and
rerun after primary_sources.tsv grows. A failed fetch writes a file with status 0 and the error; -retry-failed
fetches those again.

Run as a module from the repo root:
    python -m scripts.fetch_primary_sources
    python -m scripts.fetch_primary_sources -min-outlets 10      # only sources linked by 10+ outlets
    python -m scripts.fetch_primary_sources -max-files 5         # test
"""
import argparse
import csv
import glob
import json
import os

from config.paths import PRIMARY_SOURCES_PATH, PRIMARY_TEXTS_DIR
from src.file_worker import process_files
from src.source_texts import SourceFetcher, source_path
from src.warc_worker_cli import optional_int, setup_worker_process


def parse_args():
    parser = argparse.ArgumentParser(description='Fetch the raw text of the primary sources')
    parser.add_argument('-sources', default=str(PRIMARY_SOURCES_PATH))
    parser.add_argument('-out-dir', default=str(PRIMARY_TEXTS_DIR))
    parser.add_argument('-min-outlets', type=int, default=0, help='only sources linked by this many outlets')
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
    os.makedirs(args.out_dir, exist_ok=True)
    if args.retry_failed:
        retry_failed(args.out_dir)
    with open(args.sources, encoding='utf-8', newline='') as f:
        sources = {r['document']: r['href'] for r in csv.DictReader(f, delimiter='\t')
                   if int(r['outlets']) >= args.min_outlets}
    fetcher = SourceFetcher()

    def fetch(document, out_path):
        href = sources[document]
        try:
            row = fetcher.text(href)
        except Exception as exc:   # recorded, so the source isn't refetched on every run (-retry-failed does)
            row = {'status': 0, 'final_url': href, 'content_type': '', 'title': '', 'text': '', 'n_chars': 0,
                   'error': f'{type(exc).__name__}: {exc}'[:300]}
        with open(out_path + '.part', 'w', encoding='utf-8') as f:
            json.dump({'document': document, 'url': href, **row}, f, ensure_ascii=False)
        os.rename(out_path + '.part', out_path)
        return {'status': row['status'], 'chars': row['n_chars']}
    process_files(list(sources), lambda document: source_path(args.out_dir, document), fetch, args.max_files)


if __name__ == '__main__':
    main()
