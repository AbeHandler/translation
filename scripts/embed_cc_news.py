#!/usr/bin/env python
"""
A worker: news-similarity embeddings (src/news_embeddings.py, CPU) of the English CC-NEWS articles whose body says
"AI", for media-storm clustering:
    data/interim/cc_html/<warc>.parquet (+ cc_links/<warc>.jsonl) -> data/interim/cc_news_embeddings/<warc>.parquet
WARCs in random order; each one is done once across all workers (.lock files, src/file_worker.py), and a WARC
with an embeddings file is skipped, so rerun or add workers any time. The model weights are downloaded once to
$TMP/models/newsSimilarity/state_dict.tar. scripts/embed_cc_news.sh submits many workers.

Run as a module from the repo root:
    python -m scripts.embed_cc_news
    python -m scripts.embed_cc_news -max-files 1        # test: one WARC
    python -m scripts.embed_cc_news -download-only      # just fetch the model (scripts/embed_cc_news.sh runs this
                                                        # once before the workers, so they don't all download it)
"""
import argparse
import glob
import logging
import os

import torch

from config.paths import CC_HTML_DIR, CC_LINKS_DIR, CC_NEWS_EMBEDDINGS_DIR, news_similarity_weights_path
from src.file_worker import process_files
from src.news_embeddings import NewsEmbedder
from src.news_similarity import NewsSimilarityEncoder, ensure_weights
from src.warc_worker_cli import optional_int, setup_worker_process


def parse_args():
    parser = argparse.ArgumentParser(description='Embed the English CC-NEWS articles about AI')
    parser.add_argument('-html-dir', default=str(CC_HTML_DIR))
    parser.add_argument('-links-dir', default=str(CC_LINKS_DIR))
    parser.add_argument('-out-dir', default=str(CC_NEWS_EMBEDDINGS_DIR))
    parser.add_argument('-weights', default='', help='default $TMP/models/newsSimilarity/state_dict.tar')
    parser.add_argument('-min-body-ai', type=int, default=1, help='"AI" at least this often in the article body')
    parser.add_argument('-batch-size', type=int, default=16)
    parser.add_argument('-max-files', type=optional_int, default=None, help='stop after N WARCs (testing)')
    parser.add_argument('-download-only', action='store_true', help='fetch the weights and tokenizer, then exit')
    return parser.parse_args()


def main():
    setup_worker_process()  # logging; SIGTERM (scancel, time limit) exits cleanly and releases the WARC's lock
    logging.getLogger('transformers').setLevel(logging.ERROR)  # the head+tail token warning, once per article
    args = parse_args()
    torch.set_num_threads(int(os.environ.get('OMP_NUM_THREADS', torch.get_num_threads())))
    weights = ensure_weights(args.weights or str(news_similarity_weights_path()))
    encoder = NewsSimilarityEncoder(weights, args.batch_size)  # also fetches the tokenizer and config
    if args.download_only:
        print(f'model ready: {weights}')
        return
    embedder = NewsEmbedder(encoder, args.links_dir, args.min_body_ai)
    html_paths = sorted(p for p in glob.glob(os.path.join(args.html_dir, '*.parquet')) if '.max' not in p)
    os.makedirs(args.out_dir, exist_ok=True)

    def out_path(html_path):
        return os.path.join(args.out_dir, os.path.basename(html_path))
    n_done = process_files(html_paths, out_path, embedder.embed_file, max_files=args.max_files)
    n_out = len(glob.glob(os.path.join(args.out_dir, '*.parquet')))
    print(f'this worker embedded {n_done} WARCs; {n_out} of {len(html_paths)} have embeddings in {args.out_dir}')


if __name__ == '__main__':
    main()
