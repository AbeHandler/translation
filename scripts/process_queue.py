#!/usr/bin/env python
"""
One worker of a shard queue (src/shard_queue): processes every shard of -queue-dir that has no result in
-results-dir yet, in random order, skipping shards other workers have claimed, one row at a time. Start as many
workers as you like (scripts/process_queue.sh); they share the work.

Run as a module from the repo root:
    python -m scripts.process_queue -queue-dir $TMP/wikipedia_queue/zh -results-dir $TMP/wikipedia_results/zh \
        -processor fetch_status
    python -m scripts.process_queue ... -max-shards 1      # test: one shard
"""
import argparse
import logging

from src.shard_queue.processors import PROCESSORS
from src.shard_queue.worker import process_queue
from src.warc_worker_cli import optional_int, setup_worker_process


def parse_args():
    parser = argparse.ArgumentParser(description='Process a shard queue')
    parser.add_argument('-queue-dir', required=True, help='shard_*.jsonl files (src/shard_queue/shards.py)')
    parser.add_argument('-results-dir', required=True, help='one result file per shard')
    parser.add_argument('-processor', required=True, choices=sorted(PROCESSORS))
    parser.add_argument('-max-shards', type=optional_int, default=None, help='stop after N shards (testing)')
    return parser.parse_args()


def main():
    setup_worker_process()  # logging; SIGTERM (scancel, time limit) exits cleanly and releases the shard's lock
    args = parse_args()
    logging.getLogger('httpx').setLevel(logging.WARNING)  # a line per request otherwise
    process_queue(args.queue_dir, args.results_dir, PROCESSORS[args.processor], args.max_shards)


if __name__ == '__main__':
    main()
