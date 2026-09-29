"""Processing a shard queue (shards.py). Shards are claimed through src/file_worker.py, so any number of workers
can run at once; each worker does one row at a time."""
import json
import logging
import os
import time

from src.file_worker import process_files
from src.shard_queue.shards import read_shard, shard_paths

logger = logging.getLogger(__name__)


def safe(process_row):
    """process_row that returns {'error': ...} instead of raising, so one bad row doesn't lose the shard."""
    def run(row):
        try:
            return process_row(row)
        except Exception as exc:
            return {'error': f'{type(exc).__name__}: {exc}'[:500]}
    return run


def process_shard(shard_path, out_path, process_row):
    """Write out_path (atomically): one line per row of the shard, in order, row + result. Returns counts."""
    rows = read_shard(shard_path)
    started = time.time()
    results = [safe(process_row)(row) for row in rows]
    with open(out_path + '.part', 'w', encoding='utf-8') as f:
        for row, result in zip(rows, results):
            f.write(json.dumps({**row, **result}, ensure_ascii=False) + '\n')
    os.rename(out_path + '.part', out_path)
    n_errors = sum('error' in result for result in results)
    return {'rows': len(rows), 'errors': n_errors, 'seconds': round(time.time() - started, 1)}


def process_queue(queue_dir, results_dir, process_row, max_shards=None):
    """Process every shard of queue_dir without a result in results_dir. Returns the number this worker did."""
    shards = shard_paths(queue_dir)
    if not shards:
        raise FileNotFoundError(f'no shards in {queue_dir}')
    os.makedirs(results_dir, exist_ok=True)

    def out_path(shard_path):
        return os.path.join(results_dir, os.path.basename(shard_path))

    def process(shard_path, out):
        return process_shard(shard_path, out, process_row)
    n_done = process_files(shards, out_path, process, max_files=max_shards)
    n_results = sum(os.path.exists(out_path(s)) for s in shards)
    logger.info('this worker did %d shards; %d of %d shards have results', n_done, n_results, len(shards))
    return n_done
