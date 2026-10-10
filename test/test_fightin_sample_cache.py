"""Run from the repo root: python -m pytest test/"""
import types

import pyarrow as pa
import pyarrow.parquet as pq

from src.fightin.sample_cache import SampleCache


def test_save_load_and_key(tmp_path):
    cache = SampleCache(str(tmp_path / 'c'), {'version': 3, 'n': 10})
    assert cache.load() == ([], set(), False)
    cache.save([{'url': 'a'}], {'0:f1'})
    cache.save([{'url': 'b'}], {'0:f1', '0:f2'}, complete=True)
    docs, done, complete = SampleCache(str(tmp_path / 'c'), {'version': 3, 'n': 10}).load()
    assert [d['url'] for d in docs] == ['a', 'b'] and done == {'0:f1', '0:f2'} and complete
    assert SampleCache(str(tmp_path / 'c'), {'version': 4, 'n': 10}).load() == ([], set(), False)   # rules changed


def test_sampling_resumes_after_an_interruption(tmp_path, monkeypatch):
    import scripts.fightin as f
    monkeypatch.setattr(f, 'CHECKPOINT_FILES', 1)
    files = []
    for k in range(6):
        path = tmp_path / f'w{k}.parquet'
        pq.write_table(pa.Table.from_pylist([{'url': f'https://o{k}.com/{i}', 'language': 'en', 'html': 'x'}
                                             for i in range(3)]), path)
        files.append(str(path))
    args = types.SimpleNamespace(out=str(tmp_path / 'exp'), n=12, selection='all', per_file=2, seed=0, min_docs=1)
    calls = []

    def read_doc(row):
        calls.append(row['url'])
        if len(calls) == 7:
            raise KeyboardInterrupt      # the time limit, mid-file
        return {'title': '', 'text': row['url']}
    try:
        f.sample_language(files, read_doc, 'en', args)
    except KeyboardInterrupt:
        pass
    before = len(calls)
    docs = f.sample_language(files, read_doc, 'en', args)
    assert len(docs) == 12 and len({d['url'] for d in docs}) == 12
    assert len(calls) - before < 12              # the resumed run didn't start over
