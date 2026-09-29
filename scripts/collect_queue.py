#!/usr/bin/env python
"""
Collect a shard queue's results (src/shard_queue/collect.py): every result in <queue-dir>/results, deduplicated
by -key (default srcpage,url; a success beats an error) -> -out (JSONL). Prints how complete the queue is and a
count of each value of -count (default language) and of the error types. scripts/process_queue.sh submits it
after its workers; run it any time to see where things stand.

Run as a module from the repo root:
    python -m scripts.collect_queue -queue-dir $TMP/cc_news_queue -out data/processed/news_link_languages.jsonl
"""
import argparse
from collections import Counter

from src.shard_queue.collect import collect_results, queue_status, write_jsonl


def parse_args():
    parser = argparse.ArgumentParser(description="Collect a shard queue's results, deduplicated")
    parser.add_argument('-queue-dir', required=True)
    parser.add_argument('-out', required=True, help='JSONL of the deduplicated results')
    parser.add_argument('-key', default='srcpage,url', help='fields that identify a row')
    parser.add_argument('-count', default='language', help='field to count the values of')
    return parser.parse_args()


def main():
    args = parse_args()
    status = queue_status(args.queue_dir)
    rows = collect_results(args.queue_dir, args.key.split(','))
    write_jsonl(rows, args.out)
    errors = [row['error'] for row in rows if 'error' in row]
    print(f"queue: {status['done']} of {status['shards']} shards done, {status['missing']} missing, "
          f"{status['locks']} locked (in progress, or left by a killed worker)")
    print(f'{len(rows)} unique rows ({len(errors)} errors) -> {args.out}')
    print(f'\n{args.count}:')
    for value, n in Counter(row.get(args.count, 'ERROR' if 'error' in row else None) for row in rows).most_common():
        print(f'  {n:8d}  {value}')
    print('\nerrors:')
    for value, n in Counter(error.split(':')[0] for error in errors).most_common(10):
        print(f'  {n:8d}  {value}')
    if status['missing'] or errors:
        print('\nTo finish: rerun the workers for missing shards; rebuild the queue (FRESH=1) to retry the errors.')


if __name__ == '__main__':
    main()
