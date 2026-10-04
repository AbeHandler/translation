#!/usr/bin/env python
"""
Every English screenshot found so far in the site crawls' screened images (scripts/screen_site_crawl_images.py),
one TSV line each: kind (tweet/prose), site, page, image URL, OCR confidence, OCR text (first -ocr-chars).
    data/interim/site_crawls/*/images/*.jsonl -> data/processed/english_screenshot_links.tsv
Safe while screening runs (reads finished files only); rerun for the newest.

Run as a module from the repo root:
    python -m scripts.export_english_screenshots
"""
import argparse
import csv
import glob
import json
import os
from collections import Counter
from urllib.parse import urlparse

from config.paths import SITE_CRAWLS_DIR, NEWS_EN_ZH_LINKS_PATH

COLUMNS = ['kind', 'site', 'page', 'src', 'latin_conf', 'ocr']


def parse_args():
    parser = argparse.ArgumentParser(description='Export the English screenshots found in the site crawls')
    parser.add_argument('-crawls-dir', default=str(SITE_CRAWLS_DIR))
    parser.add_argument('-out', default=os.path.join(os.path.dirname(str(NEWS_EN_ZH_LINKS_PATH)),
                                                     'english_screenshot_links.tsv'))
    parser.add_argument('-ocr-chars', type=int, default=300)
    return parser.parse_args()


def screenshot_rows(paths, ocr_chars):
    """One row per English screenshot in the screened-images JSONL files."""
    for path in paths:
        with open(path, encoding='utf-8') as f:
            for line in f:
                page = json.loads(line)
                for image in page['images']:
                    if image.get('english_screenshot'):
                        yield {'kind': image.get('english_kind') or 'old rule',
                               'site': urlparse(page['url']).netloc, 'page': page['url'], 'src': image['src'],
                               'latin_conf': image.get('latin_conf'),
                               'ocr': ' '.join((image.get('ocr_text') or '').split())[:ocr_chars]}


def main():
    args = parse_args()
    paths = sorted(glob.glob(os.path.join(args.crawls_dir, '*', 'images', '*.jsonl')))
    rows = sorted(screenshot_rows(paths, args.ocr_chars), key=lambda r: (r['kind'], r['site'], r['page']))
    with open(args.out + '.part', 'w', encoding='utf-8', newline='') as f:
        writer = csv.DictWriter(f, COLUMNS, delimiter='\t')
        writer.writeheader()
        writer.writerows(rows)
    os.rename(args.out + '.part', args.out)
    print(f'{len(paths)} screened files -> {len(rows)} English screenshots -> {args.out}')
    print('by kind:', dict(Counter(r['kind'] for r in rows)))
    print('top sites:', Counter(r['site'] for r in rows).most_common(10))
    print(f'spot check: grep -P "^tweet\\t" {args.out} | cut -f4 | shuf -n 10')


if __name__ == '__main__':
    main()
