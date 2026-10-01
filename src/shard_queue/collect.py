"""
Collecting a shard queue's results (queue_dir/results/*.jsonl) into one deduplicated set. Results accumulate:
a row can have several results (retries after errors, reprocessing), so they are merged by the row's key fields:
the first successful result is kept and errors are only counted. One streaming pass: tens of millions of
results never sit in memory, only an 8-byte hash per key. Also reports how complete the queue is.
"""
import glob
import hashlib
import json
import logging
import os

from src.shard_queue.shards import read_shard, results_dir, shard_paths

logger = logging.getLogger(__name__)
PROGRESS_EVERY = 500  # files


def queue_status(queue_dir):
    """{shards, done, missing, locks}: queued shards, how many have a result, how many don't, in-progress locks."""
    out = results_dir(queue_dir)
    shards = shard_paths(queue_dir)
    done = sum(os.path.exists(os.path.join(out, os.path.basename(s))) for s in shards)
    return {'shards': len(shards), 'done': done, 'missing': len(shards) - done,
            'locks': len(glob.glob(os.path.join(out, '*.lock')))}


def key_hash(result, key_fields):
    key = json.dumps([result.get(field) for field in key_fields], ensure_ascii=False)
    return hashlib.blake2b(key.encode(), digest_size=8).digest()


def collect_results(queue_dir, key_fields, errors=None):
    """Yield the first successful result per key (the tuple of key_fields). Errors are not yielded: a row that
    only failed has no result; errors (a Counter, if given) counts them by type."""
    paths = sorted(glob.glob(os.path.join(results_dir(queue_dir), '*.jsonl')))
    seen = set()
    for n, path in enumerate(paths, 1):
        if n % PROGRESS_EVERY == 0 or n == len(paths):
            logger.info('%d/%d result files read, %d unique rows so far', n, len(paths), len(seen))
        for result in read_shard(path):
            if 'error' in result:
                if errors is not None:
                    errors[result['error'].split(':')[0]] += 1
                continue
            key = key_hash(result, key_fields)
            if key not in seen:
                seen.add(key)
                yield result


def write_jsonl(rows, out_path):
    """Write rows (any iterable) atomically. Returns how many."""
    os.makedirs(os.path.dirname(os.path.abspath(out_path)), exist_ok=True)
    n = 0
    with open(out_path + '.part', 'w', encoding='utf-8') as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False) + '\n')
            n += 1
    os.rename(out_path + '.part', out_path)
    return n
