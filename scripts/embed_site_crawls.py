#!/usr/bin/env python
"""
Driver: sentence embeddings (CPU) for every page the scrapy crawls saved:
    data/interim/site_crawls/<domain>/html/<part>.parquet -> <domain>/embeddings/<part>.parquet
one embeddings file per HTML file (src/embed_html.py has the format). HTML files that already have one are
skipped, so rerun it as the crawls write more. scripts/embed_site_crawls.sh submits many copies to SLURM;
they share the work through .lock files.

Run as a module from the repo root, so `src` and `config` import:
    python -m scripts.embed_site_crawls
    python -m scripts.embed_site_crawls -max-files 1    # test
"""
import argparse
import glob
import logging
import os

from sentence_transformers import SentenceTransformer

from config.paths import SITE_CRAWLS_DIR
from src.embed_html import HtmlEmbedder, embed_all
from src.warc_worker_cli import optional_int, setup_worker_process

MODEL_NAME = 'BAAI/bge-base-zh-v1.5'


def parse_args():
    """SLURM passes unset optional values as '', so optional flags treat '' as their default."""
    parser = argparse.ArgumentParser(description='Embed the pages saved by the scrapy crawls')
    parser.add_argument('-crawls-dir', default=str(SITE_CRAWLS_DIR), help='one subdirectory per site')
    parser.add_argument('-model', default=MODEL_NAME, help='a sentence-transformers model on Hugging Face')
    parser.add_argument('-batch-size', type=int, default=32)
    parser.add_argument('-max-files', type=optional_int, default=None, help='stop after N HTML files (testing)')
    return parser.parse_args()


def embeddings_path(html_path):
    """<domain>/html/<part>.parquet -> <domain>/embeddings/<part>.parquet"""
    site_dir = os.path.dirname(os.path.dirname(html_path))
    return os.path.join(site_dir, 'embeddings', os.path.basename(html_path))


def main():
    setup_worker_process()
    logging.getLogger('jieba').setLevel(logging.WARNING)
    args = parse_args()
    html_paths = sorted(glob.glob(os.path.join(args.crawls_dir, '*', 'html', '*.parquet')))
    if not html_paths:
        raise FileNotFoundError(f'no HTML Parquet files under {args.crawls_dir}/*/html/')
    model = SentenceTransformer(args.model, device='cpu')
    embedder = HtmlEmbedder(model, args.model, batch_size=args.batch_size)
    n_done = embed_all(html_paths, embeddings_path, embedder, max_files=args.max_files)
    logging.info('this worker embedded %d files', n_done)
    crawls = args.crawls_dir
    print('\nSpot checks:')
    print(f'  ls {crawls}/*/html/*.parquet | wc -l; ls {crawls}/*/embeddings/*.parquet | wc -l   # equal when done')
    print(f"  python -c \"import pyarrow.parquet as pq, glob; f = glob.glob('{crawls}/*/embeddings/*')[0]; "
          "t = pq.read_table(f); print(t.schema.metadata, t.num_rows, len(t['embedding'][0]))\"")


if __name__ == '__main__':
    main()
