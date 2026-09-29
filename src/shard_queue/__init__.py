"""
A queue of rows (dicts) kept as shard files on a shared filesystem, and a worker that processes it. Built for
many workers at once (e.g. hundreds of SLURM jobs), with no database or server:

    shards.py  write_shards(rows, queue_dir): rows, shuffled, as queue_dir/shard_00000.jsonl, ... (1000 rows each)
    worker.py  process_queue(queue_dir, results_dir, process_row): every shard without a result, in random order,
               each claimed with a .lock (src/file_worker.py) and processed one row at a time; results go to
               results_dir/<shard>.jsonl, one line per input row: the row, plus what process_row returned, or an
               "error" field. One worker is one process; to go faster, run more workers.

process_row(row) -> dict is whatever the use needs, e.g. src/link_language (fetch the url, label its language).
A worker that dies leaves no partial result; its shard is redone by the next worker (release its lock if it was
killed hard). scripts/process_queue.py runs a worker with a named processor; scripts/process_queue.sh submits many.
"""
