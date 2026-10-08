"""Run from the repo root: python -m pytest test/"""
import pandas as pd

from src.fightin.contexts import dedupe, evidence, snippet, unit_regex


def test_dedupe_syndicated_copies():
    docs = pd.DataFrame({
        'lang': ['en', 'en', 'en', 'zh', 'zh'],
        'title': ['Consortium Selects BlackBerry', 'Consortium selects BlackBerry!', 'Other', '首页', '首页'],
        'text': ['WATERLOO /PRNewswire/ ...', 'Waterloo, PRNewswire ...', 'A different story', '第一篇', '第二篇']})
    kept, dropped = dedupe(docs)
    assert list(kept.index) == [0, 2, 3, 4] and dropped == {'en': 1}     # same Chinese title, different texts: kept


def test_unit_regex_and_snippet():
    assert unit_regex('blackberry qnx', 'en').search('the BlackBerry® QNX platform')
    assert unit_regex('baidu发布', 'zh').search(' Baidu 发布 ERNIE Bot')
    text = 'x' * 300 + ' AI safety ' + 'y' * 300
    assert snippet(text, unit_regex('ai safety', 'en'), width=5) == '…xxxx AI safety yyyy…'


def test_evidence_examples_from_different_outlets():
    docs = pd.DataFrame({'url': ['u1', 'u2', 'u3'], 'outlet': ['a.com', 'a.com', 'b.com'], 'title': ['', '', ''],
                         'text': ['AI safety one', 'AI safety two', 'more AI safety']})
    e = evidence(docs, ['ai safety'], 'en')
    assert e['documents'] == 3 and e['outlets'] == 2 and [x['outlet'] for x in e['examples']] == ['a.com', 'b.com']
