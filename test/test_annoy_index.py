"""Run from the repo root: python -m pytest test/"""
import pyarrow as pa
import pyarrow.parquet as pq
import pytest

from src.annoy_index import build_annoy_index, load_annoy_index
from src.embed_html import SCHEMA


def write_embeddings(path, vectors, model='m'):
    rows = [{'record_id': f'r{i}', 'url': f'https://example.com/{i}', 'language': 'zh',
             'text_chars': 0 if v is None else 10, 'embedding': v} for i, v in enumerate(vectors)]
    pq.write_table(pa.Table.from_pylist(rows, SCHEMA.with_metadata({'model': model})), path)


def test_builds_index_skipping_null_embeddings(tmp_path):
    write_embeddings(tmp_path / 'a.parquet', [[1.0, 0.0], None, [0.0, 1.0]])
    write_embeddings(tmp_path / 'b.parquet', [[0.9, 0.1]])
    files = [('a.com', str(tmp_path / 'a.parquet')), ('b.com', str(tmp_path / 'b.parquet'))]
    info = build_annoy_index(files, str(tmp_path / 'out'), n_trees=2)
    index, ids, _ = load_annoy_index(str(tmp_path / 'out'))
    assert info['items'] == 3 and info['dimensions'] == 2 and info['domains'] == 2
    assert ids['url'].to_pylist() == ['https://example.com/0', 'https://example.com/2', 'https://example.com/0']
    assert index.get_nns_by_item(0, 2) == [0, 2]  # [1, 0] is nearest to [0.9, 0.1]


def test_refuses_mixed_models(tmp_path):
    write_embeddings(tmp_path / 'a.parquet', [[1.0, 0.0]], model='m1')
    write_embeddings(tmp_path / 'b.parquet', [[1.0, 0.0]], model='m2')
    files = [('a.com', str(tmp_path / 'a.parquet')), ('b.com', str(tmp_path / 'b.parquet'))]
    with pytest.raises(ValueError, match='one model'):
        build_annoy_index(files, str(tmp_path / 'out'))
