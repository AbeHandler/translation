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


def test_a_fresh_rebuild_keeps_results_and_queues_nothing_already_done(tmp_path):
    from src.shard_queue.shards import clear_queue
    rows = [{'url': f'u{i}'} for i in range(4)]
    add_to_queue(rows, str(tmp_path / 'q'), shard_size=10)
    assert process_queue(str(tmp_path / 'q'), lambda row: {'ok': 1}) == 1
    clear_queue(str(tmp_path / 'q'))
    assert shard_paths(str(tmp_path / 'q')) == [] and len(list((tmp_path / 'q' / 'results').glob('*.jsonl'))) == 1
    assert add_to_queue(rows, str(tmp_path / 'q'), shard_size=10) == (0, 4)


def test_rows_already_done_are_not_queued_again_but_failed_ones_are(tmp_path):
    from src.shard_queue.shards import clear_queue
    rows = [{'srcpage': 'p', 'url': f'u{i}'} for i in range(3)]
    add_to_queue(rows, str(tmp_path / 'q'), shard_size=10)

    def process_row(row):
        if row['url'] == 'u1':
            raise ValueError('timeout')
        return {'language': 'en'}
    process_queue(str(tmp_path / 'q'), process_row)
    clear_queue(str(tmp_path / 'q'))
    assert add_to_queue(rows + [{'srcpage': 'p', 'url': 'u9'}], str(tmp_path / 'q')) == (2, 2)  # u1 retried, u9 new
    queued = sorted(r['url'] for p in shard_paths(str(tmp_path / 'q')) for r in read_shard(p))
    assert queued == ['u1', 'u9']


def test_collect_dedupes_by_key_and_prefers_success(tmp_path):
    from src.shard_queue.collect import collect_results, queue_status
    add_to_queue([{'srcpage': 'p', 'url': f'u{i}'} for i in range(2)], str(tmp_path / 'q'))
    results = tmp_path / 'q' / 'results'
    results.mkdir()
    (results / 'a.jsonl').write_text('{"srcpage": "p", "url": "u0", "error": "timeout"}\n'
                                     '{"srcpage": "p", "url": "u1", "language": "zh"}\n', encoding='utf-8')
    (results / 'b.jsonl').write_text('{"srcpage": "p", "url": "u0", "language": "en"}\n'
                                     '{"srcpage": "p", "url": "u1", "error": "timeout"}\n', encoding='utf-8')
    rows = collect_results(str(tmp_path / 'q'), ['srcpage', 'url'])
    assert sorted((r['url'], r.get('language')) for r in rows) == [('u0', 'en'), ('u1', 'zh')]
    assert queue_status(str(tmp_path / 'q')) == {'shards': 1, 'done': 0, 'missing': 1, 'locks': 0}


def test_key_fields_ignore_extra_fields(tmp_path):
    add_to_queue([{'srcpage': 'p', 'url': 'u1'}], str(tmp_path / 'q'))
    rows = [{'srcpage': 'p', 'src_language': 'en', 'url': 'u1'}, {'srcpage': 'p', 'src_language': 'en', 'url': 'u2'}]
    assert add_to_queue(rows, str(tmp_path / 'q'), key_fields=('srcpage', 'url')) == (1, 1)
