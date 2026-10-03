#!/usr/bin/env python
"""
A worker: screen the images of the Chinese site crawls' AI articles for English screenshots (src/clip.py: each
image fetched into memory, CLIP class, OCR if it may be text, then dropped):
    data/interim/site_crawls/<domain>/html/<part>.parquet -> <domain>/images/<part>.jsonl
one row per page about AI {url, n_images, n_english_screenshots, images: [{src, alt, label, ocr_text, latin,
english_screenshot, ...}]}: image URLs, never images. HTML files in random order, each done once across workers
(.lock files), files with an images file skipped, so rerun it as the crawls write more.
scripts/screen_site_crawl_images.sh submits many workers.

Run as a module from the repo root (TESSDATA_PREFIX must point at the eng + chi_sim files):
    python -m scripts.screen_site_crawl_images
    python -m scripts.screen_site_crawl_images -max-files 1        # test: one HTML file
"""
import argparse
import glob
import os

import httpx

from config.paths import SITE_CRAWLS_DIR
from src.clip import ImageClassifier, screen_html_file, tesseract_ocr
from src.file_worker import process_files
from src.warc_worker_cli import optional_int, setup_worker_process


def parse_args():
    parser = argparse.ArgumentParser(description="Screen the site crawls' AI articles for English screenshots")
    parser.add_argument('-crawls-dir', default=str(SITE_CRAWLS_DIR), help='one subdirectory per site')
    parser.add_argument('-all-pages', action='store_true', help='screen every page, not only pages about AI')
    parser.add_argument('-max-files', type=optional_int, default=None, help='stop after N HTML files (testing)')
    return parser.parse_args()


def images_path(html_path):
    """<domain>/html/<part>.parquet -> <domain>/images/<part>.jsonl"""
    site_dir = os.path.dirname(os.path.dirname(html_path))
    return os.path.join(site_dir, 'images', os.path.basename(html_path).removesuffix('.parquet') + '.jsonl')


def main():
    setup_worker_process()  # logging; SIGTERM (scancel, time limit) exits cleanly and releases the file's lock
    args = parse_args()
    classifier, client = ImageClassifier(), httpx.Client()
    html_paths = sorted(glob.glob(os.path.join(args.crawls_dir, '*', 'html', '*.parquet')))

    def screen(html_path, out_path):
        return screen_html_file(html_path, out_path, classifier, tesseract_ocr, client, ai_only=not args.all_pages)
    n_done = process_files(html_paths, images_path, screen, args.max_files)
    print(f'this worker screened {n_done} HTML files; '
          f'{sum(os.path.exists(images_path(p)) for p in html_paths)} of {len(html_paths)} are done')


if __name__ == '__main__':
    main()
