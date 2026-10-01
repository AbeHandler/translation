#!/usr/bin/env python
"""
Queue the Chinese pages English articles link to, one row per distinct URL, for fetching as documents
(src/zh_docs.py): the cleaned English -> Chinese link files (scripts/clean_en_zh_links.py) -> $TMP/zh_docs_queue.
Adds only URLs not queued or done yet, so rerun it after new links are cleaned. Then:
    bash scripts/process_queue.sh zh_docs        # fetch them -> data/processed/zh_docs.jsonl

Run as a module from the repo root:
    python -m scripts.zh_docs_queue
    python -m scripts.zh_docs_queue -links data/processed/news_en_zh_links_clean.jsonl
"""
import argparse
import json
import os

from config.paths import NEWS_EN_ZH_LINKS_PATH, zh_docs_queue_dir
from src.shard_queue.shards import add_to_queue

PROCESSED = os.path.dirname(NEWS_EN_ZH_LINKS_PATH)
CLEAN_LINKS = [os.path.join(PROCESSED, name) for name in
               ('news_en_zh_links_clean.jsonl', 'cc_full_en_zh_links_clean.jsonl')]


def parse_args():
    parser = argparse.ArgumentParser(description='Queue the linked Chinese pages for fetching as documents')
    parser.add_argument('-links', nargs='+', default=CLEAN_LINKS, help='cleaned link files (missing ones skipped)')
    parser.add_argument('-queue-dir', default='', help='default $TMP/zh_docs_queue')
    return parser.parse_args()


def main():
    args = parse_args()
    urls = set()
    for path in args.links:
        if not os.path.exists(path):
            print(f'skipping {path}: not there')
            continue
        with open(path, encoding='utf-8') as f:
            urls.update(json.loads(line)['url'] for line in f)
    if not urls:
        raise FileNotFoundError(f'no links in {args.links}; run scripts/clean_en_zh_links.py first')
    queue_dir = args.queue_dir or str(zh_docs_queue_dir())
    added, already = add_to_queue([{'url': url} for url in sorted(urls)], queue_dir, shard_size=100,
                                  key_fields=('url',))
    print(f'{len(urls)} distinct Chinese URLs: {added} queued, {already} already queued or done, in {queue_dir}')
    print('Fetch them: bash scripts/process_queue.sh zh_docs')


if __name__ == '__main__':
    main()
