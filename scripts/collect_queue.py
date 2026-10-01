#!/usr/bin/env python
"""
Collect a shard queue's results (src/shard_queue/collect.py): every result in <queue-dir>/results, deduplicated
by -key (default srcpage,url; a success beats an error) -> -out (JSONL), only the rows matching -where (e.g.
'src_language=en&language=zh': English articles' links to Chinese pages). Prints how complete the queue is and a
count of each value of -count (default language) and of the error types, over all rows.
scripts/process_queue.sh submits it after its workers; run it any time to see where things stand.

Run as a module from the repo root:
    python -m scripts.collect_queue -queue-dir $TMP/cc_news_queue -out data/processed/news_en_zh_links.jsonl \
        -where 'src_language=en&language=zh'
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
    parser.add_argument('-where', default='', help="field=value&field=value: keep only rows matching all; '' = all")
    return parser.parse_args()


def parse_where(where):
    """'src_language=en&language=zh' -> {'src_language': 'en', 'language': 'zh'}"""
    return dict(part.split('=', 1) for part in where.split('&') if part)


def main():
    args = parse_args()
    status = queue_status(args.queue_dir)
    where = parse_where(args.where)
    values, errors = Counter(), Counter()

    def counted_and_kept(rows):  # counts every row as they stream past (never all in memory), keeps the matches
        for row in rows:
            values[row.get(args.count, 'ERROR' if 'error' in row else None)] += 1
            if 'error' in row:
                errors[row['error'].split(':')[0]] += 1
            if all(row.get(field) == value for field, value in where.items()):
                yield row
    n_kept = write_jsonl(counted_and_kept(collect_results(args.queue_dir, args.key.split(','))), args.out)
    print(f"queue: {status['done']} of {status['shards']} shards done, {status['missing']} missing, "
          f"{status['locks']} locked (in progress, or left by a killed worker)")
    print(f'{sum(values.values())} unique rows ({sum(errors.values())} errors); {n_kept} '
          f'{"matching " + args.where if where else ""} -> {args.out}')
    print(f'\n{args.count}:')
    for value, n in values.most_common():
        print(f'  {n:8d}  {value}')
    print('\nerrors:')
    for value, n in errors.most_common(10):
        print(f'  {n:8d}  {value}')
    if status['missing'] or errors:
        print('\nTo finish: rerun the workers for missing shards; rebuild the queue (FRESH=1) to retry the errors.')


if __name__ == '__main__':
    main()
