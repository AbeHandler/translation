"""Run from the repo root: python -m pytest test/"""
import pandas as pd

from src.fightin.select import doc_id, read_ids, select_ids, write_ids

DOCS = pd.DataFrame({'url': ['u1', 'u2', 'u3', 'u4'], 'title': ['OpenAI news', '', '', ''],
                     'text': ['...', 'openai said', 'Anthropic Claude', 'nothing'],
                     'date': ['2025-01-05', '2025-03-01', '', '2025-02-01']})


def test_pattern_is_case_insensitive_on_title_and_text():
    assert select_ids(DOCS, 'OpenAI') == [doc_id('u1'), doc_id('u2')]
    assert select_ids(DOCS, 'Anthropic|Claude') == [doc_id('u3')]


def test_date_span_leaves_out_undated():
    assert select_ids(DOCS, start='2025-02-01') == [doc_id('u2'), doc_id('u4')]
    assert select_ids(DOCS, 'openai', end='2025-01-31') == [doc_id('u1')]


def test_ids_round_trip(tmp_path):
    write_ids(['a', 'b'], tmp_path / 'ids.txt')
    assert read_ids(tmp_path / 'ids.txt') == {'a', 'b'}
