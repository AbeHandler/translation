#!/usr/bin/env python
"""
The external links of CC-NEWS articles about AI, as a shard queue (src/shard_queue) for scripts/process_queue.sh:
    data/interim/cc_html/<warc>.parquet (HTML) + cc_links/<warc>.jsonl (body links)
        -> $TMP/cc_news_queue/shard_*.jsonl   {srcpage: the article's url, src_language, url: the link},
           shuffled, 1000 per shard
An article counts as about AI when its visible text says "AI" as a word at least -min-ai-mentions times
(src/ai_mentions.py, the rule the other queues use). Needs only the html and links steps, not NER. Only WARCs
with both an HTML and a links file are read (it says how many have HTML but no links yet). Adds only links not
queued or done yet (src/shard_queue/shards.py), so rerun it as more WARCs get links; the queue workers then only
do the new shards. -fresh deletes the queue's shards first (results are kept), e.g. after raising
-min-ai-mentions.

Run as a module from the repo root:
    python -m scripts.cc_news_queue                                    # every WARC there is
    python -m scripts.cc_news_queue -start-date 20260223 -end-date 20260302 -min-ai-mentions 2
"""
import argparse
import datetime
import os

from config.paths import CC_HTML_DIR, CC_LINKS_DIR, cc_news_queue_dir
from src.cc_news import ai_article_links, warc_files
from src.shard_queue.shards import SHARD_SIZE, add_to_queue, clear_queue
from src.warc_worker_cli import optional_date, optional_int

ALL_DATES = (datetime.date(1900, 1, 1), datetime.date(2999, 12, 31))


def parse_args():
    parser = argparse.ArgumentParser(description='External links of CC-NEWS articles about AI, as a shard queue')
    parser.add_argument('-html-dir', default=str(CC_HTML_DIR))
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
    html_paths = warc_files(args.html_dir, '.parquet', start, end, args.max_n)
    pairs, missing = [], 0
    for html_path in html_paths:
        links_path = os.path.join(args.links_dir, os.path.basename(html_path).removesuffix('.parquet') + '.jsonl')
        if os.path.exists(links_path):
            pairs.append((html_path, links_path))
        else:
            missing += 1
    if not pairs:
        raise FileNotFoundError(f'no WARC has both an HTML file ({args.html_dir}) and a links file ({args.links_dir})')
    rows = []
    for n, (html_path, links_path) in enumerate(pairs, 1):
        rows += ai_article_links(html_path, links_path, args.min_ai_mentions)
        if n % 50 == 0:
            print(f'{n}/{len(pairs)} WARCs read, {len(rows)} links so far', flush=True)
    queue_dir = args.queue_dir or str(cc_news_queue_dir())
    if args.fresh:
        clear_queue(queue_dir)
    # keyed on (srcpage, url), so results from before src_language was added still count as done
    added, already = add_to_queue(rows, queue_dir, args.shard_size, key_fields=('srcpage', 'url'))
    print(f'{len(pairs)} WARCs ({missing} with HTML but no links file yet): {len(rows)} links from '
          f'{len({r["srcpage"] for r in rows})} AI articles; {added} new ones queued '
          f'({already} already queued or done) in {queue_dir}')
    print('Process them: bash scripts/process_queue.sh news')


if __name__ == '__main__':
    main()
