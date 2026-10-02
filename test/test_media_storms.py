"""Run from the repo root: python -m pytest test/"""
import numpy as np
import pyarrow as pa
import pyarrow.parquet as pq

from src.media_storms import DAY_SCHEMA, clusters, day_edges, shift, storms, write_edges


def write_day(days_dir, date, rows):
    (days_dir / date).mkdir(parents=True, exist_ok=True)
    pq.write_table(pa.Table.from_pylist(rows, DAY_SCHEMA), days_dir / date / 'W.parquet')


def row(url, vec, outlet='a.com'):
    v = np.asarray(vec, dtype=float)
    return {'url': url, 'outlet': outlet, 'title': url, 'vector': (v / np.linalg.norm(v)).tolist()}


def test_edges_link_similar_articles_within_the_window_once(tmp_path):
    write_day(tmp_path, '2023-07-13', [row('x1', [1, 0, 0]), row('x2', [1, 0.05, 0]), row('y1', [0, 1, 0])])
    write_day(tmp_path, '2023-07-16', [row('x3', [1, 0, 0.02])])
    write_day(tmp_path, '2023-07-25', [row('x4', [1, 0, 0])])         # outside the 8-day window
    edges = day_edges(str(tmp_path), '2023-07-13')
    assert sorted((a, b) for a, b, _ in edges) == [('x1', 'x2'), ('x1', 'x3'), ('x2', 'x3')]
    write_edges(edges, str(tmp_path / 'e.parquet'))
    assert clusters([str(tmp_path / 'e.parquet')]) == {'x1': 'x1', 'x2': 'x1', 'x3': 'x1'}


def test_a_storm_needs_a_week_and_five_outlets_in_storm_mode():
    articles, cluster_of = [], {}
    for o in range(6):                                   # 6 outlets, 50 articles a day each
        for d in range(10):
            date = shift('2023-07-10', d)
            for k in range(50):
                url = f'o{o}-{d}-{k}'
                articles.append({'url': url, 'outlet': f'outlet{o}.com', 'date': date})
                if k < 3:                                # 3 of 50 a day (6%) are about the story
                    cluster_of[url] = 'story'
    found = storms(articles, cluster_of)
    assert len(found) == 1 and found[0]['storm_outlets'] == 6 and found[0]['days'] == 10
    short = {u: c for u, c in cluster_of.items() if u.split('-')[1] in '012'}   # 3 days only
    assert storms(articles, short) == []
