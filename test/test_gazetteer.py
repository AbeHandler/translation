"""Run from the repo root: python -m pytest test/"""
import json

import pyarrow as pa
import pyarrow.parquet as pq
import pytest

from src.gazetteer import Gazetteer, read_gazetteer, write_stories
from src.ner_html import SCHEMA as NER_SCHEMA

ENTRIES = {'Dario Amodei': ['Dario Amodei', 'Amodei'], 'Claude': ['Claude'], 'DeepSeek': ['DeepSeek']}


def entity(text, label='ORG', start=0):
    return {'text': text, 'label': label, 'start_char': start, 'end_char': start + len(text)}


def test_whole_word_case_insensitive_any_label_longest_form_reported():
    gazetteer = Gazetteer(ENTRIES)
    found = gazetteer.matches([entity('Dario Amodei', 'PERSON'), entity('claude code', 'PRODUCT'),
                               entity('Claudette', 'PERSON'), entity('Reuters')])
    assert [(m['canonical'], m['form'], m['ner_label']) for m in found] == [
        ('Dario Amodei', 'Dario Amodei', 'PERSON'), ('Claude', 'claude', 'PRODUCT')]
    assert gazetteer.matches(None) == []


def test_gazetteer_file_is_checked(tmp_path):
    (tmp_path / 'g.yaml').write_text('A: [Same]\nB: [same]\n', encoding='utf-8')
    with pytest.raises(ValueError, match='both'):
        read_gazetteer(tmp_path / 'g.yaml')
    (tmp_path / 'g.yaml').write_text('A:\n', encoding='utf-8')
    with pytest.raises(ValueError, match='needs a list'):
        read_gazetteer(tmp_path / 'g.yaml')


def test_stories_keep_text_matches_and_warc_date(tmp_path):
    ner = [{'record_id': 'r0', 'url': 'u0', 'language': 'en', 'text': 'Title\nDeepSeek said.', 'ner_chars': 20,
            'entities': [entity('DeepSeek', start=6)]},
           {'record_id': 'r1', 'url': 'u1', 'language': 'en', 'text': 'Other\nNothing.', 'ner_chars': 14,
            'entities': [entity('Reuters')]},
           {'record_id': 'r2', 'url': 'u2', 'language': 'zh', 'text': '中文', 'ner_chars': 0, 'entities': None}]
    name = 'CC-NEWS-20260224000000-00001.parquet'
    pq.write_table(pa.Table.from_pylist(ner, NER_SCHEMA), tmp_path / f'ner_{name}')
    pq.write_table(pa.table({'record_id': ['r0', 'r1', 'r2'], 'warc_date': ['d0', 'd1', 'd2']}),
                   tmp_path / f'html_{name}')
    counts, n = write_stories([(str(tmp_path / f'ner_{name}'), str(tmp_path / f'html_{name}'))],
                              Gazetteer(ENTRIES), str(tmp_path / 'out' / 's.jsonl'))
    (story,) = [json.loads(line) for line in open(tmp_path / 'out' / 's.jsonl', encoding='utf-8')]
    assert n == 1 and counts == {'DeepSeek': 1}
    assert (story['record_id'], story['title'], story['warc_date']) == ('r0', 'Title', 'd0')
    assert story['canonicals'] == ['DeepSeek']
    m = story['matches'][0]
    assert story['text'][m['start_char']:m['end_char']] == 'DeepSeek'
