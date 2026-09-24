#!/usr/bin/env python
"""
Driver: one Annoy index over every embeddings file the scrapy crawls have (scripts/embed_site_crawls.py),
    data/interim/site_crawls/*/embeddings/*.parquet -> data/processed/site_crawls_annoy/
                                                        index.ann, ids.parquet, info.json
Always a full rebuild that replaces the old index (src/annoy_index.py), so rerun it to take in new embeddings.
Prints a few random pages' nearest neighbours as a spot check.

Run as a module from the repo root, so `src` and `config` import:
    python -m scripts.build_annoy_index
    python -m scripts.build_annoy_index -n-trees 10 -out-dir /tmp/annoy_test   # quick test
"""
import argparse
import glob
import json
import logging
import os
import random

from config.paths import SITE_CRAWLS_ANNOY_DIR, SITE_CRAWLS_DIR
from src.annoy_index import build_annoy_index, load_annoy_index


def parse_args():
    parser = argparse.ArgumentParser(description='Build one Annoy index over the site crawl embeddings')
    parser.add_argument('-crawls-dir', default=str(SITE_CRAWLS_DIR), help='one subdirectory per site')
    parser.add_argument('-out-dir', default=str(SITE_CRAWLS_ANNOY_DIR))
    parser.add_argument('-n-trees', type=int, default=50, help='more trees: better recall, bigger index')
    return parser.parse_args()


def embedding_files(crawls_dir):
    """(domain, path) for every <crawls_dir>/<domain>/embeddings/*.parquet."""
    paths = sorted(glob.glob(os.path.join(crawls_dir, '*', 'embeddings', '*.parquet')))
    if not paths:
        raise FileNotFoundError(f'no embeddings files under {crawls_dir}/*/embeddings/')
    return [(os.path.basename(os.path.dirname(os.path.dirname(path))), path) for path in paths]


def print_spot_checks(out_dir, n_pages=3, n_neighbours=5):
    index, ids, info = load_annoy_index(out_dir)
    urls = ids.column('url').to_pylist()
    print(json.dumps(info, indent=2))
    for item in random.sample(range(len(urls)), min(n_pages, len(urls))):
        print(f'\nneighbours of {urls[item]}')
        neighbours, distances = index.get_nns_by_item(item, n_neighbours + 1, include_distances=True)
        for neighbour, distance in zip(neighbours[1:], distances[1:]):
            cosine = 1 - distance ** 2 / 2  # angular distance is sqrt(2 - 2 cos)
            print(f'  {cosine:.3f}  {urls[neighbour]}')


def main():
    logging.basicConfig(level=logging.INFO)
    args = parse_args()
    files = embedding_files(args.crawls_dir)
    logging.info('building from %d embeddings files', len(files))
    info = build_annoy_index(files, args.out_dir, n_trees=args.n_trees)
    logging.info('built %s', info)
    print_spot_checks(args.out_dir)


if __name__ == '__main__':
    main()
