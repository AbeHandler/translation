"""Run from the repo root: python -m pytest test/"""
import json

from src.shard_queue.shards import add_to_queue, read_shard, shard_paths
from src.shard_queue.worker import process_queue


def test_queue_holds_every_row_shuffled_and_only_grows(tmp_path):
    rows = [{'srcpage': 'p', 'url': f'https://x.com/{i}'} for i in range(25)]
    assert add_to_queue(rows, str(tmp_path / 'q'), shard_size=10) == (25, 0)
    paths = shard_paths(str(tmp_path / 'q'))
    assert sorted(len(read_shard(p)) for p in paths) == [5, 10, 10]
    back = [row for p in paths for row in read_shard(p)]
    assert sorted(r['url'] for r in back) == sorted(r['url'] for r in rows) and back != rows
    more = rows + [{'srcpage': 'p', 'url': 'https://x.com/new'}]
    assert add_to_queue(more, str(tmp_path / 'q'), shard_size=10) == (1, 25)  # only the new row, as a new shard
    assert set(paths) < set(shard_paths(str(tmp_path / 'q')))  # existing shards untouched


def test_worker_keeps_rows_in_order_records_errors_and_skips_done_shards(tmp_path):
    add_to_queue([{'url': f'u{i}'} for i in range(5)], str(tmp_path / 'q'), shard_size=2)
    calls = []

    def process_row(row):
        calls.append(row['url'])
        if row['url'] == 'u3':
            raise ValueError('boom')
        return {'n': len(row['url'])}
    assert process_queue(str(tmp_path / 'q'), process_row) == 3
    results = [json.loads(line) for p in sorted((tmp_path / 'q' / 'results').glob('shard_*.jsonl'))
               for line in open(p)]
    queued = [row for p in shard_paths(str(tmp_path / 'q')) for row in read_shard(p)]
    assert [r['url'] for r in results] == [r['url'] for r in queued]
    assert next(r for r in results if r['url'] == 'u3')['error'] == 'ValueError: boom'
    assert process_queue(str(tmp_path / 'q'), process_row) == 0 and len(calls) == 5


def test_a_fresh_rebuild_keeps_results_and_reuses_them_for_identical_shards(tmp_path):
    from src.shard_queue.shards import clear_queue
    rows = [{'url': f'u{i}'} for i in range(4)]
    add_to_queue(rows, str(tmp_path / 'q'), shard_size=10)
    assert process_queue(str(tmp_path / 'q'), lambda row: {'ok': 1}) == 1
    clear_queue(str(tmp_path / 'q'))
    assert shard_paths(str(tmp_path / 'q')) == [] and len(list((tmp_path / 'q' / 'results').glob('*.jsonl'))) == 1
    add_to_queue(rows, str(tmp_path / 'q'), shard_size=10)  # same content -> same shard name -> result reused
    assert process_queue(str(tmp_path / 'q'), lambda row: {'ok': 1}) == 0
