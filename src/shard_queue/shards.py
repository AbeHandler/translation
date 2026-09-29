"""Writing and reading queue shards: JSONL files of shard_size rows, named shard_00000.jsonl, ... in queue_dir."""
import glob
import json
import os
import random
import shutil

SHARD_SIZE = 1000


def write_shards(rows, queue_dir, shard_size=SHARD_SIZE, seed=0):
    """Replace queue_dir with the rows, shuffled (so any prefix of the work is a random sample), in shards.
    Built in queue_dir.part and swapped in whole, so a queue is never half-written. Returns the number of shards."""
    rows = list(rows)
    random.Random(seed).shuffle(rows)
    part = queue_dir.rstrip('/') + '.part'
    shutil.rmtree(part, ignore_errors=True)
    os.makedirs(part)
    for n, start in enumerate(range(0, len(rows), shard_size)):
        with open(os.path.join(part, f'shard_{n:05d}.jsonl'), 'w', encoding='utf-8') as f:
            for row in rows[start:start + shard_size]:
                f.write(json.dumps(row, ensure_ascii=False) + '\n')
    shutil.rmtree(queue_dir, ignore_errors=True)
    os.rename(part, queue_dir)
    return (len(rows) + shard_size - 1) // shard_size


def shard_paths(queue_dir):
    return sorted(glob.glob(os.path.join(queue_dir, 'shard_*.jsonl')))


def read_shard(path):
    with open(path, encoding='utf-8') as f:
        return [json.loads(line) for line in f]
