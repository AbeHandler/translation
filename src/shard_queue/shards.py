"""
Writing and reading queue shards: JSONL files of up to shard_size rows in queue_dir, named after their content
(shard_<hash>.jsonl). A queue only grows: add_to_queue writes only rows that aren't in it yet, as new shards, and
never touches existing ones, so results already made for a shard stay valid and a rerun of the worker only
processes the new shards. Content names mean a result can never be mistaken for another shard's.

Results live in the queue: queue_dir/results/<shard name> (src/shard_queue/worker.py). clear_queue removes the
shards but keeps the results, so after a fresh rebuild any shard with the same content reuses its result.
"""
import glob
import hashlib
import json
import os
import random

SHARD_SIZE = 1000


def row_key(row):
    return json.dumps(row, ensure_ascii=False, sort_keys=True)


def results_dir(queue_dir):
    return os.path.join(queue_dir, 'results')


def shard_paths(queue_dir):
    return sorted(glob.glob(os.path.join(queue_dir, 'shard_*.jsonl')))


def read_shard(path):
    with open(path, encoding='utf-8') as f:
        return [json.loads(line) for line in f]


def add_to_queue(rows, queue_dir, shard_size=SHARD_SIZE, seed=0):
    """Add the rows not already queued, shuffled (so any prefix of the work is a random sample), as new shards.
    Returns (rows added, rows already queued)."""
    os.makedirs(queue_dir, exist_ok=True)
    queued = {row_key(row) for path in shard_paths(queue_dir) for row in read_shard(path)}
    new = {}
    for row in rows:
        key = row_key(row)
        if key not in queued:
            new[key] = row
    new_rows = list(new.values())
    random.Random(seed).shuffle(new_rows)
    for start in range(0, len(new_rows), shard_size):
        lines = ''.join(json.dumps(row, ensure_ascii=False) + '\n' for row in new_rows[start:start + shard_size])
        path = os.path.join(queue_dir, f'shard_{hashlib.sha1(lines.encode()).hexdigest()[:16]}.jsonl')
        with open(path + '.part', 'w', encoding='utf-8') as f:
            f.write(lines)
        os.rename(path + '.part', path)
    return len(new_rows), len(queued)


def clear_queue(queue_dir):
    """Delete a queue's shards, for a fresh start (e.g. after narrowing what goes in it). Its results are kept:
    a shard that comes back with the same content (so the same name) reuses its result."""
    for path in shard_paths(queue_dir):
        os.remove(path)
