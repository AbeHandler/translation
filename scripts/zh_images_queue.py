#!/usr/bin/env python
"""
Queue the Chinese documents (zh_docs, is_document) for screening their images for English screenshots
(src/clip.py ZhImageScreener): data/processed/zh_docs.jsonl -> $TMP/zh_images_queue, 20 documents a shard.
Adds only documents not queued or done yet. Then:
    bash scripts/process_queue.sh zh_images        # -> data/processed/zh_images.jsonl (image URLs, never images)

Run as a module from the repo root:
    python -m scripts.zh_images_queue
"""
import argparse
import json

from config.paths import ZH_DOCS_PATH, zh_images_queue_dir
from src.shard_queue.shards import add_to_queue


def parse_args():
    parser = argparse.ArgumentParser(description='Queue the Chinese documents for image screening')
    parser.add_argument('-zh-docs', default=str(ZH_DOCS_PATH))
    parser.add_argument('-queue-dir', default='', help='default $TMP/zh_images_queue')
    return parser.parse_args()


def main():
    args = parse_args()
    with open(args.zh_docs, encoding='utf-8') as f:
        urls = sorted({d['url'] for d in map(json.loads, f) if d.get('is_document')})
    queue_dir = args.queue_dir or str(zh_images_queue_dir())
    added, already = add_to_queue([{'url': u} for u in urls], queue_dir, shard_size=20, key_fields=('url',))
    print(f'{len(urls)} Chinese documents: {added} queued, {already} already queued or done, in {queue_dir}')


if __name__ == '__main__':
    main()
