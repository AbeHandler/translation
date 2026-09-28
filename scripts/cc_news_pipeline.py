#!/usr/bin/env python
"""
The CC-NEWS pipeline for a date range, in steps (-step), each reading only the previous step's output
(src/cc_news.py has the details):
    download  WARCs -> $TMP/cc_news_warcs/ (scratch; delete them whenever). Optional: html downloads what it
              needs anyway; this just gets a date range's WARCs ahead of time.
    html   WARCs -> data/interim/cc_html/<warc>.parquet   raw en/zh article HTML; the only step that reads WARCs
    links  cc_html/<warc>.parquet -> data/interim/cc_links/<warc>.jsonl   each article's body links
    ner    cc_html/<warc>.parquet -> data/interim/cc_ner/<warc>.parquet   each English article's text and named
           entities (spaCy en_core_web_trf on CPU, nlp.pipe; src/ner_html.py), for gazetteer filtering later
    match  cc_links -> data/processed/cc_link_matches.jsonl   links to the seeds in config/seed_patterns.txt,
           including URL-encoded redirect links. Refuses unless every WARC in the range has its links file
           (-partial to match what there is).

download, html, links and ner are worker steps: scripts/go.sh submits many copies to SLURM, which share the work through
.lock/.done files. Every step skips work already done, so it is safe to stop and rerun; a new seed pattern
only needs -step match. Clean slate: sbatch --export=NONE scripts/slurm/flush_cc_news.slurm

Run as a module from the repo root, so `src` and `config` import:
    python -m scripts.cc_news_pipeline -step download -start-date 20260901 -end-date 20260923
    python -m scripts.cc_news_pipeline -step html -start-date 20260901 -end-date 20260923
    python -m scripts.cc_news_pipeline -step ner -start-date 20260901 -end-date 20260923
    python -m scripts.cc_news_pipeline -step links -start-date 20260901 -end-date 20260923
    python -m scripts.cc_news_pipeline -step match -start-date 20260901 -end-date 20260923
    python -m scripts.cc_news_pipeline -step html -start-date 20260923 -end-date 20260923 -max-warcs 1 -max-n 100
"""
import argparse
import os

from config.paths import (CC_HTML_DIR, CC_LINK_MATCHES_PATH, CC_LINKS_DIR, CC_NER_DIR, SEED_PATTERNS_PATH,
                          download_warcs_work_dir, extract_warc_html_work_dir, warc_cache_dir)
from src.cc_news import (ArticleHtmlArchiver, ArticleLinkExtractor, CCNewsIndex, HtmlArchivePipeline, WarcWorker,
                         WorkDir, match_seed_links, read_patterns, warc_files, warc_name, with_max_n)
from src.file_worker import process_files
from src.warc_worker_cli import add_warc_worker_args, setup_worker_process

STEPS = ('download', 'html', 'links', 'ner', 'match')


def parse_args():
    parser = argparse.ArgumentParser(description='The CC-NEWS pipeline: download, html, links, ner, match')
    parser.add_argument('-step', required=True, choices=STEPS)
    add_warc_worker_args(parser, default_work_dir_help='html step; default $TMP/extract_warc_html')
    parser.add_argument('-html-dir', default=str(CC_HTML_DIR))
    parser.add_argument('-links-dir', default=str(CC_LINKS_DIR))
    parser.add_argument('-ner-dir', default=str(CC_NER_DIR))
    parser.add_argument('-patterns', default=str(SEED_PATTERNS_PATH), help='one substring per line')
    parser.add_argument('-matches-path', default='', help=f'default {CC_LINK_MATCHES_PATH}')
    parser.add_argument('-partial', action='store_true', help='match: even if some WARCs have no links yet')
    return parser.parse_args()


def index(args):
    return CCNewsIndex(args.warc_cache_dir or str(warc_cache_dir()), args.aws)


def download(args):
    """Just fetch the WARCs into the cache; the .done files only record that they are there."""
    worker = WarcWorker(index=index(args), work_dir=WorkDir(str(download_warcs_work_dir()), args.max_n),
                        max_warcs=args.max_warcs)
    keys = worker.list_warcs(args.start_date, args.end_date)
    worker.process_all(keys, lambda key, local_warc: {'bytes': os.path.getsize(local_warc)})


def html(args):
    worker = WarcWorker(index=index(args), work_dir=WorkDir(args.work_dir or str(extract_warc_html_work_dir()),
                                                            args.max_n),
                        max_warcs=args.max_warcs)
    HtmlArchivePipeline(worker, ArticleHtmlArchiver(max_n=args.max_n), args.html_dir).run(args.start_date,
                                                                                          args.end_date)


def html_paths_for(args):
    paths = warc_files(args.html_dir, '.parquet', args.start_date, args.end_date, args.max_n)
    if not paths:
        raise FileNotFoundError(f'no HTML Parquet files for {args.start_date}..{args.end_date} in {args.html_dir}; '
                                'run -step html first')
    return paths


def from_each_html_file(args, out_dir, ext, write):
    """Run write(html_path, out_path) for every HTML file of the range without an output in out_dir."""
    html_paths = html_paths_for(args)

    def out_path(html_path):
        return os.path.join(out_dir, os.path.basename(html_path).removesuffix('.parquet') + ext)
    n_done = process_files(html_paths, out_path, write, max_files=args.max_warcs)
    print(f'this worker wrote {n_done} files to {out_dir}; '
          f'{sum(os.path.exists(out_path(p)) for p in html_paths)} of {len(html_paths)} HTML files have one')


def links(args):
    from_each_html_file(args, args.links_dir, '.jsonl', ArticleLinkExtractor().write)


def ner(args):
    from src.ner_html import EntityExtractor, load_ner_model  # spaCy loads only for this step
    from_each_html_file(args, args.ner_dir, '.parquet', EntityExtractor(load_ner_model()).write)


def match(args):
    keys = index(args).list_warcs(args.start_date, args.end_date)
    patterns = read_patterns(args.patterns)
    matches_path = args.matches_path or with_max_n(str(CC_LINK_MATCHES_PATH), args.max_n)

    def links_path(key):
        return os.path.join(args.links_dir, with_max_n(warc_name(key), args.max_n) + '.jsonl')
    counts = match_seed_links(keys, links_path, patterns, matches_path, partial=args.partial)
    print(f'{len(keys)} WARCs, {args.start_date}..{args.end_date} -> {matches_path}')
    for pattern in patterns:
        print(f'  {counts[pattern]:6d}  {pattern}')
    print('\nSpot checks:')
    print(f'  jq -r .pattern {matches_path} | sort | uniq -c')
    print(f"  jq -c '{{href, decoded, url, language}}' {matches_path} | head")


def main():
    setup_worker_process()
    args = parse_args()
    {'download': download, 'html': html, 'links': links, 'ner': ner, 'match': match}[args.step](args)


if __name__ == '__main__':
    main()
