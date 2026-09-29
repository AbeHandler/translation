"""Run from the repo root: python -m pytest test/"""
import json

from src.shard_queue.shards import read_shard, shard_paths, write_shards
from src.shard_queue.worker import process_queue


def test_shards_hold_every_row_shuffled(tmp_path):
    rows = [{'srcpage': 'p', 'url': f'https://x.com/{i}'} for i in range(25)]
    assert write_shards(rows, str(tmp_path / 'q'), shard_size=10) == 3
    paths = shard_paths(str(tmp_path / 'q'))
    assert [len(read_shard(p)) for p in paths] == [10, 10, 5]
    back = [row for p in paths for row in read_shard(p)]
    assert sorted(r['url'] for r in back) == sorted(r['url'] for r in rows) and back != rows
    assert write_shards(rows[:3], str(tmp_path / 'q'), shard_size=10) == 1  # a rebuild replaces the old queue
    assert len(shard_paths(str(tmp_path / 'q'))) == 1


def test_worker_keeps_rows_in_order_records_errors_and_skips_done_shards(tmp_path):
    write_shards([{'url': f'u{i}'} for i in range(5)], str(tmp_path / 'q'), shard_size=2)
    calls = []

    def process_row(row):
        calls.append(row['url'])
        if row['url'] == 'u3':
            raise ValueError('boom')
        return {'n': len(row['url'])}
    assert process_queue(str(tmp_path / 'q'), str(tmp_path / 'r'), process_row) == 3
    results = [json.loads(line) for p in sorted((tmp_path / 'r').glob('shard_*.jsonl')) for line in open(p)]
    queued = [row for p in shard_paths(str(tmp_path / 'q')) for row in read_shard(p)]
    assert [r['url'] for r in results] == [r['url'] for r in queued]
    assert next(r for r in results if r['url'] == 'u3')['error'] == 'ValueError: boom'
    assert process_queue(str(tmp_path / 'q'), str(tmp_path / 'r'), process_row) == 0 and len(calls) == 5
