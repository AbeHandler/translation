#!/usr/bin/env python
"""
Driver: every CC-NEWS story that names an entry of config/gazetteer.yaml among its named entities, with its
text and matches, in one JSONL (src/gazetteer.py has the format):
    data/interim/cc_ner/<warc>.parquet (+ cc_html for warc_date) -> data/processed/gazetteer_stories.jsonl
Rebuilds the whole file every run (edit the gazetteer, rerun). Reads every NER file, or those of a date range.

Run as a module from the repo root:
    python -m scripts.filter_by_gazetteer
    python -m scripts.filter_by_gazetteer -start-date 20260223 -end-date 20260302
    python -m scripts.filter_by_gazetteer -max-n 100      # the test files (.max100) only
"""
import argparse
import datetime
import logging
import os

from config.paths import CC_HTML_DIR, CC_NER_DIR, GAZETTEER_PATH, GAZETTEER_STORIES_PATH
from src.cc_news import warc_files, with_max_n
from src.gazetteer import Gazetteer, read_gazetteer, write_stories
from src.warc_worker_cli import optional_int, parse_date


def parse_args():
    parser = argparse.ArgumentParser(description='CC-NEWS stories naming gazetteer entries, with their text')
    parser.add_argument('-gazetteer', default=str(GAZETTEER_PATH))
    parser.add_argument('-ner-dir', default=str(CC_NER_DIR))
    parser.add_argument('-html-dir', default=str(CC_HTML_DIR))
    parser.add_argument('-out', default='', help=f'default {GAZETTEER_STORIES_PATH}')
    parser.add_argument('-start-date', type=parse_date, default=datetime.date(2000, 1, 1), help='YYYYMMDD')
    parser.add_argument('-end-date', type=parse_date, default=datetime.date(2100, 1, 1), help='YYYYMMDD')
    parser.add_argument('-max-n', type=optional_int, default=None, help='use the .max<N> test files')
    return parser.parse_args()


def main():
    logging.basicConfig(level=logging.INFO)
    args = parse_args()
    entries = read_gazetteer(args.gazetteer)
    ner_paths = warc_files(args.ner_dir, '.parquet', args.start_date, args.end_date, args.max_n)
    if not ner_paths:
        raise FileNotFoundError(f'no NER files in {args.ner_dir} for that range; run the ner step first')
    pairs = [(path, os.path.join(args.html_dir, os.path.basename(path))) for path in ner_paths]
    out = args.out or with_max_n(str(GAZETTEER_STORIES_PATH), args.max_n)
    counts, n_stories = write_stories(pairs, Gazetteer(entries), out)
    print(f'{n_stories} stories from {len(ner_paths)} NER files -> {out}')
    for canonical in entries:
        print(f'  {counts.get(canonical, 0):7d}  {canonical}')
    print('\nSpot checks:')
    print(f"  head -1 {out} | python -m json.tool | head -40")
    print(f"  jq -c '{{url, canonicals}}' {out} | head")
    print(f"  jq -r '.matches[] | [.canonical, .entity, .ner_label] | @tsv' {out} | sort | uniq -c | sort -rn "
          "| head -30   # what each entry matched")


if __name__ == '__main__':
    main()
