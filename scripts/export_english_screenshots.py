#!/usr/bin/env python
"""
Every English screenshot found so far in the site crawls' screened images (scripts/screen_site_crawl_images.py),
one TSV line each: kind (tweet/prose), site, page, image URL, OCR confidence, whether it is by a notable account,
the notable accounts in it, and the OCR text (first -ocr-chars).
    data/interim/site_crawls/*/images/*.jsonl -> data/processed/english_screenshot_links.tsv
notable: a notable account's @handle is in the screenshot, or a tweet carries a notable person's name
(src/notable_accounts.py; needs scripts/fetch_notable_accounts.py first). accounts lists every match as
name @handle (Wikipedia editions, matched by handle or name): in prose a name match is a mention, not the author.
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

from config.paths import (ENGLISH_SCREENSHOTS_PATH, NOTABLE_ACCOUNTS_EXTRA_PATH, NOTABLE_ACCOUNTS_PATH,
                          SITE_CRAWLS_DIR)
from src.notable_accounts import NotableAccounts

COLUMNS = ['kind', 'site', 'page', 'src', 'latin_conf', 'notable', 'max_sitelinks', 'accounts', 'ocr']


def parse_args():
    parser = argparse.ArgumentParser(description='Export the English screenshots found in the site crawls')
    parser.add_argument('-crawls-dir', default=str(SITE_CRAWLS_DIR))
    parser.add_argument('-out', default=str(ENGLISH_SCREENSHOTS_PATH))
    parser.add_argument('-accounts', nargs='+', default=[str(NOTABLE_ACCOUNTS_PATH), str(NOTABLE_ACCOUNTS_EXTRA_PATH)])
    parser.add_argument('-ocr-chars', type=int, default=300)
    return parser.parse_args()


def notable_columns(kind, ocr, accounts):
    """{notable, max_sitelinks, accounts} for one screenshot's OCR text."""
    found = accounts.match(ocr)
    by = [m for m in found if m['how'] == 'handle' or kind == 'tweet']
    return {'notable': int(bool(by)), 'max_sitelinks': max((m['sitelinks'] for m in by), default=0),
            'accounts': '; '.join(f"{m['name']} @{m['handle']} ({m['sitelinks']}, {m['how']})" for m in found)}


def screenshot_rows(paths, ocr_chars, accounts):
    """One row per English screenshot in the screened-images JSONL files."""
    for path in paths:
        with open(path, encoding='utf-8') as f:
            for line in f:
                page = json.loads(line)
                for image in page['images']:
                    if image.get('english_screenshot'):
                        kind, ocr = image.get('english_kind') or 'old rule', ' '.join((image['ocr_text'] or '').split())
                        yield {'kind': kind, 'site': urlparse(page['url']).netloc, 'page': page['url'],
                               'src': image['src'], 'latin_conf': image.get('latin_conf'),
                               **notable_columns(kind, ocr, accounts), 'ocr': ocr[:ocr_chars]}


def main():
    args = parse_args()
    accounts = NotableAccounts.from_files(*args.accounts)
    paths = sorted(glob.glob(os.path.join(args.crawls_dir, '*', 'images', '*.jsonl')))
    rows = sorted(screenshot_rows(paths, args.ocr_chars, accounts),
                  key=lambda r: (r['kind'], -r['notable'], -r['max_sitelinks'], r['site'], r['page']))
    with open(args.out + '.part', 'w', encoding='utf-8', newline='') as f:
        writer = csv.DictWriter(f, COLUMNS, delimiter='\t')
        writer.writeheader()
        writer.writerows(rows)
    os.rename(args.out + '.part', args.out)
    print(f'{len(paths)} screened files -> {len(rows)} English screenshots -> {args.out}')
    print('by kind:', dict(Counter(r['kind'] for r in rows)))
    print('notable, by kind:', dict(Counter(r['kind'] for r in rows if r['notable'])))
    print('top sites:', Counter(r['site'] for r in rows).most_common(10))
    print('most frequent notable accounts:', Counter(
        a.split(' (')[0] for r in rows if r['notable'] for a in r['accounts'].split('; ')).most_common(15))
    print(f'spot check: awk -F"\\t" \'$6 == 1\' {args.out} | cut -f1,8 | shuf -n 10')


if __name__ == '__main__':
    main()
