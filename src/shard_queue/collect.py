"""
Collecting a shard queue's results (queue_dir/results/*.jsonl) into one deduplicated set. Results accumulate:
a row can have several results (retries after errors, reprocessing), so they are merged by the row's key fields,
a successful result winning over an error. Also reports how complete the queue is.
"""
import glob
import json
import os

from src.shard_queue.shards import read_shard, results_dir, shard_paths


def queue_status(queue_dir):
    """{shards, done, missing, locks}: queued shards, how many have a result, how many don't, in-progress locks."""
    out = results_dir(queue_dir)
    shards = shard_paths(queue_dir)
    done = sum(os.path.exists(os.path.join(out, os.path.basename(s))) for s in shards)
    return {'shards': len(shards), 'done': done, 'missing': len(shards) - done,
            'locks': len(glob.glob(os.path.join(out, '*.lock')))}


def collect_results(queue_dir, key_fields):
    """One result per key (the tuple of key_fields), preferring a successful one over an error."""
    best = {}
    for path in sorted(glob.glob(os.path.join(results_dir(queue_dir), '*.jsonl'))):
        for result in read_shard(path):
            key = tuple(result.get(field) for field in key_fields)
            if key not in best or ('error' in best[key] and 'error' not in result):
                best[key] = result
    return list(best.values())


def write_jsonl(rows, out_path):
    os.makedirs(os.path.dirname(os.path.abspath(out_path)), exist_ok=True)
    with open(out_path + '.part', 'w', encoding='utf-8') as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False) + '\n')
    os.rename(out_path + '.part', out_path)
