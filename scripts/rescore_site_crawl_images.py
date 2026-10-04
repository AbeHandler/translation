#!/usr/bin/env python
"""
Re-apply the English-screenshot test (src/clip.py english_kind: a tweet with an @handle, or English prose) to the
images already screened in the site crawls, from their saved OCR text: nothing is fetched or OCR'd again. Rewrites
data/interim/site_crawls/<domain>/images/<part>.jsonl in place (via .part). Files rows of which have no latin_conf
(screened before it was recorded) can't pass the confidence check, so their images come out as not English.

Run as a module from the repo root:
    python -m scripts.rescore_site_crawl_images
"""
import argparse
import glob
import json
import os

from config.paths import SITE_CRAWLS_DIR
from src.clip import rescore_row


def parse_args():
    parser = argparse.ArgumentParser(description='Re-apply the English-screenshot test to the saved OCR')
    parser.add_argument('-crawls-dir', default=str(SITE_CRAWLS_DIR))
    return parser.parse_args()


def main():
    args = parse_args()
    paths = sorted(glob.glob(os.path.join(args.crawls_dir, '*', 'images', '*.jsonl')))
    before = after = 0
    for n, path in enumerate(paths, 1):
        with open(path, encoding='utf-8') as f:
            rows = [json.loads(line) for line in f]
        before += sum(r['n_english_screenshots'] for r in rows)
        rows = [rescore_row(r) for r in rows]
        after += sum(r['n_english_screenshots'] for r in rows)
        with open(path + '.part', 'w', encoding='utf-8') as f:
            f.writelines(json.dumps(r, ensure_ascii=False) + '\n' for r in rows)
        os.rename(path + '.part', path)
        if n % 1000 == 0:
            print(f'{n}/{len(paths)} files', flush=True)
    print(f'{len(paths)} files rescored: {before} English screenshots before, {after} now')


if __name__ == '__main__':
    main()
