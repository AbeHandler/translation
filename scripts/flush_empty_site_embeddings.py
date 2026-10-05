#!/usr/bin/env python
"""
FLUSH: delete the site crawls' embeddings files in which more than -max-empty of the pages have no embedding, so
scripts/embed_site_crawls.sh embeds them again. A one-off fix: before src/embed_html.py cut languages to two
letters, every page declaring zh-CN, zh-Hans or en-US got no embedding (newspaper4k refused the code), about half
of all pages. Files deleted in random order. Run once, not on every pipeline run: a file whose pages really have
no text would be re-embedded each time.

Run as a module from the repo root:
    python -m scripts.flush_empty_site_embeddings -dry-run     # count only
    python -m scripts.flush_empty_site_embeddings
"""
import argparse
import glob
import os
import random

import pyarrow.compute as pc
import pyarrow.parquet as pq

from config.paths import SITE_CRAWLS_DIR


def parse_args():
    parser = argparse.ArgumentParser(description='Delete embeddings files with many pages left unembedded')
    parser.add_argument('-crawls-dir', default=str(SITE_CRAWLS_DIR))
    parser.add_argument('-max-empty', type=float, default=0.1, help='share of pages without an embedding')
    parser.add_argument('-dry-run', action='store_true')
    return parser.parse_args()


def empty_share(path):
    chars = pq.read_table(path, columns=['text_chars']).column('text_chars')
    return pc.sum(pc.equal(chars, 0)).as_py() / max(len(chars), 1)


def main():
    args = parse_args()
    paths = glob.glob(os.path.join(args.crawls_dir, '*', 'embeddings', '*.parquet'))
    random.shuffle(paths)
    flushed = 0
    for n, path in enumerate(paths, 1):
        if empty_share(path) > args.max_empty:
            flushed += 1
            if not args.dry_run:
                os.remove(path)
        if n % 2000 == 0:
            print(f'{n}/{len(paths)} checked, {flushed} over {args.max_empty:.0%} empty', flush=True)
    print(f'{flushed} of {len(paths)} embeddings files {"would be " if args.dry_run else ""}deleted '
          f'(more than {args.max_empty:.0%} of pages without an embedding)')


if __name__ == '__main__':
    main()
