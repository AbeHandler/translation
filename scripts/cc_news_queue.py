#!/usr/bin/env python
"""
The external links of CC-NEWS articles about AI, as a shard queue (src/shard_queue) for scripts/process_queue.sh:
    data/interim/cc_ner/<warc>.parquet (text) + cc_links/<warc>.jsonl (body links)
        -> $TMP/cc_news_queue/shard_*.jsonl   {srcpage: the article's url, url: the link}, shuffled, 1000 per shard
An article counts as about AI when its text says "AI" as a word at least -min-ai-mentions times
(src/ai_mentions.py, the rule the Wikipedia queue uses). Only WARCs with both a NER and a links file are read
(it says how many are missing either). Adds only links not queued yet (src/shard_queue/shards.py), so rerun it
as more WARCs get links, and rerun the queue workers with the same results dir: they only do the new shards.
-fresh deletes the queue first (e.g. after raising -min-ai-mentions).

Run as a module from the repo root:
    python -m scripts.cc_news_queue                                    # every WARC there is
    python -m scripts.cc_news_queue -start-date 20260223 -end-date 20260302 -min-ai-mentions 2
"""
import argparse
import datetime
import os

from config.paths import CC_LINKS_DIR, CC_NER_DIR, cc_news_queue_dir
from src.cc_news import ai_article_links, warc_files
from src.shard_queue.shards import SHARD_SIZE, add_to_queue, clear_queue
from src.warc_worker_cli import optional_date, optional_int

ALL_DATES = (datetime.date(1900, 1, 1), datetime.date(2999, 12, 31))


def parse_args():
    parser = argparse.ArgumentParser(description='External links of CC-NEWS articles about AI, as a shard queue')
    parser.add_argument('-ner-dir', default=str(CC_NER_DIR))
    parser.add_argument('-links-dir', default=str(CC_LINKS_DIR))
    parser.add_argument('-queue-dir', default='', help='default $TMP/cc_news_queue')
    parser.add_argument('-min-ai-mentions', type=int, default=1)
    parser.add_argument('-shard-size', type=int, default=SHARD_SIZE)
    parser.add_argument('-start-date', type=optional_date, default=None, help='YYYYMMDD; default: every WARC')
    parser.add_argument('-end-date', type=optional_date, default=None, help='YYYYMMDD')
    parser.add_argument('-max-n', type=optional_int, default=None, help='the .max<N> test files')
    parser.add_argument('-fresh', action='store_true', help='delete the queue first instead of adding to it')
    return parser.parse_args()


def main():
    args = parse_args()
    start, end = args.start_date or ALL_DATES[0], args.end_date or ALL_DATES[1]
    ner_paths = warc_files(args.ner_dir, '.parquet', start, end, args.max_n)
    pairs, missing = [], 0
    for ner_path in ner_paths:
        links_path = os.path.join(args.links_dir, os.path.basename(ner_path).removesuffix('.parquet') + '.jsonl')
        if os.path.exists(links_path):
            pairs.append((ner_path, links_path))
        else:
            missing += 1
    if not pairs:
        raise FileNotFoundError(f'no WARC has both a NER file ({args.ner_dir}) and a links file ({args.links_dir})')
    rows = [row for ner_path, links_path in pairs
            for row in ai_article_links(ner_path, links_path, args.min_ai_mentions)]
    queue_dir = args.queue_dir or str(cc_news_queue_dir())
    if args.fresh:
        clear_queue(queue_dir)
    added, already = add_to_queue(rows, queue_dir, args.shard_size)
    print(f'{len(pairs)} WARCs ({missing} with NER but no links file yet): {len(rows)} links from '
          f'{len({r["srcpage"] for r in rows})} AI articles; {added} new ones queued '
          f'({already} already queued or done) in {queue_dir}')
    print('Process them: bash scripts/process_queue.sh news')


if __name__ == '__main__':
    main()
