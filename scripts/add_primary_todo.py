#!/usr/bin/env python
"""
Add URLs to the primary-source store's to-do list (data/interim/primary/todo.tsv: url, added_from, added_at;
src/source_texts.py), each once (by its normalized key). scripts/fetch_primary_sources.py then fetches whatever on
the list has no file yet. Any list of URLs can feed it:
    -primary-sources TSV     the primary sources (data/processed/primary_sources.tsv, column href), linked by at
                             least -min-outlets outlets
    -tsv FILE -column NAME   any TSV with a URL column (e.g. -tsv data/processed/cac_links.tsv -column cac_url)
    -urls FILE               one URL per line

Run as a module from the repo root:
    python -m scripts.add_primary_todo -primary-sources data/processed/primary_sources.tsv
    python -m scripts.add_primary_todo -urls my_urls.txt
"""
import argparse
import csv
import datetime
import os

from config.paths import PRIMARY_TEXTS_DIR
from src.source_texts import TODO_COLUMNS, read_todo, source_key


def parse_args():
    parser = argparse.ArgumentParser(description="Add URLs to the primary-source store's to-do list")
    parser.add_argument('-primary-sources', help='primary_sources.tsv (column href)')
    parser.add_argument('-min-outlets', type=int, default=0, help='-primary-sources: linked by this many outlets')
    parser.add_argument('-tsv', help='a TSV with a URL column (-column)')
    parser.add_argument('-column', default='url')
    parser.add_argument('-urls', help='a file with one URL per line')
    parser.add_argument('-store-dir', default=str(PRIMARY_TEXTS_DIR))
    args = parser.parse_args()
    if not (args.primary_sources or args.tsv or args.urls):
        parser.error('give -primary-sources, -tsv or -urls')
    return args


def candidate_urls(args):
    """(url, added_from) pairs from the given lists."""
    if args.primary_sources:
        with open(args.primary_sources, encoding='utf-8', newline='') as f:
            for r in csv.DictReader(f, delimiter='\t'):
                if int(r['outlets']) >= args.min_outlets:
                    yield r['href'], os.path.basename(args.primary_sources)
    if args.tsv:
        with open(args.tsv, encoding='utf-8', newline='') as f:
            for r in csv.DictReader(f, delimiter='\t'):
                if r.get(args.column):
                    yield r[args.column], os.path.basename(args.tsv)
    if args.urls:
        with open(args.urls, encoding='utf-8') as f:
            for line in f:
                if line.strip():
                    yield line.strip(), os.path.basename(args.urls)


def main():
    args = parse_args()
    os.makedirs(args.store_dir, exist_ok=True)
    path = os.path.join(args.store_dir, 'todo.tsv')
    known = read_todo(path)
    now = datetime.datetime.now().isoformat(timespec='seconds')
    new = {}
    for url, added_from in candidate_urls(args):
        key = source_key(url)
        if key not in known and key not in new:
            new[key] = (url, added_from)
    is_new_file = not os.path.exists(path)
    with open(path, 'a', encoding='utf-8', newline='') as f:
        writer = csv.writer(f, delimiter='\t')
        if is_new_file:
            writer.writerow(TODO_COLUMNS)
        writer.writerows([url, added_from, now] for url, added_from in new.values())
    print(f'{len(new)} URLs added to {path} ({len(known) + len(new)} on the list)')


if __name__ == '__main__':
    main()
