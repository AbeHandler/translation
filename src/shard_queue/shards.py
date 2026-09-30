"""
Writing and reading queue shards: JSONL files of up to shard_size rows in queue_dir, named after their content
(shard_<hash>.jsonl). A queue only grows: add_to_queue writes only rows that aren't in it yet, as new shards, and
never touches existing ones, so results already made for a shard stay valid and a rerun of the worker only
processes the new shards. Content names mean a result can never be mistaken for another shard's.

Results live in the queue: queue_dir/results/<shard name> (src/shard_queue/worker.py), and are never deleted:
processing is the expensive part. add_to_queue skips rows that already have a successful result (rows whose
result was an error are queued again), and clear_queue removes the shards but keeps the results, so a fresh
rebuild only queues work not yet done. Results can hold the same row twice (e.g. from before this rule, or two
workers racing); dedupe when reading them, e.g. by url.
"""
import glob
import hashlib
import json
import os
import random

SHARD_SIZE = 1000


def row_key(row, fields=None):
    """The row's identity: all its fields, or only these (so extra fields don't make a done row look new)."""
    if fields is not None:
        row = {field: row.get(field) for field in fields}
    return json.dumps(row, ensure_ascii=False, sort_keys=True)


def results_dir(queue_dir):
    return os.path.join(queue_dir, 'results')


def shard_paths(queue_dir):
    return sorted(glob.glob(os.path.join(queue_dir, 'shard_*.jsonl')))


def read_shard(path):
    with open(path, encoding='utf-8') as f:
        return [json.loads(line) for line in f]


def done_keys(queue_dir, fields):
    """Row keys (over these fields) of every row with a successful result in queue_dir/results."""
    keys = set()
    for path in glob.glob(os.path.join(results_dir(queue_dir), '*.jsonl')):
        for result in read_shard(path):
            if 'error' not in result:
                keys.add(row_key(result, fields))
    return keys


def add_to_queue(rows, queue_dir, shard_size=SHARD_SIZE, seed=0, key_fields=None):
    """Add the rows not already queued and not already done, shuffled (so any prefix of the work is a random
    sample), as new shards. Rows are the same when their key_fields are (default: all fields). Returns (rows
    added, rows skipped: already queued or done)."""
    rows = list(rows)
    os.makedirs(queue_dir, exist_ok=True)
    skip = {row_key(row, key_fields) for path in shard_paths(queue_dir) for row in read_shard(path)}
    if rows:
        skip |= done_keys(queue_dir, key_fields or sorted(rows[0]))
    new = {}
    for row in rows:
        key = row_key(row, key_fields)
        if key not in skip:
            new[key] = row
    new_rows = list(new.values())
    random.Random(seed).shuffle(new_rows)
    for start in range(0, len(new_rows), shard_size):
        lines = ''.join(json.dumps(row, ensure_ascii=False) + '\n' for row in new_rows[start:start + shard_size])
        path = os.path.join(queue_dir, f'shard_{hashlib.sha1(lines.encode()).hexdigest()[:16]}.jsonl')
        with open(path + '.part', 'w', encoding='utf-8') as f:
            f.write(lines)
        os.rename(path + '.part', path)
    return len(new_rows), len(rows) - len(new_rows)


def clear_queue(queue_dir):
    """Delete a queue's shards, for a fresh start (e.g. after narrowing what goes in it). Its results are kept:
    a shard that comes back with the same content (so the same name) reuses its result."""
    for path in shard_paths(queue_dir):
        os.remove(path)
