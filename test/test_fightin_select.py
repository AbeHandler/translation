"""Run from the repo root: python -m pytest test/"""
from src.fightin.select import Selection, read_selections


def test_pattern_case_insensitive_on_title_or_text():
    s = Selection('openai', 'OpenAI|ChatGPT')
    assert s.matches('OpenAI news', '', '') and s.matches('', 'chatgpt said', '') and not s.matches('x', 'y', '')
    assert s.may_match(b'<p>OPENAI</p>') and not s.may_match(b'<p>nothing</p>') and s.may_match('<b>ChatGPT</b>')


def test_dates():
    s = Selection('h1', '', '2025-01-01', '2025-06-30')
    assert s.matches('', '', '2025-03-01') and not s.matches('', '', '2025-07-01') and not s.matches('', '', '')
    assert Selection('all').matches('', '', '') and Selection('all').may_match(b'')


def test_read_selections(tmp_path):
    (tmp_path / 's.tsv').write_text('# c\nname\tpattern\tfrom\tto\nall\nopenai\tOpenAI\t\t\n', encoding='utf-8')
    got = read_selections(tmp_path / 's.tsv')
    assert set(got) == {'all', 'openai'} and got['openai'].pattern == 'OpenAI' and got['all'].pattern == ''
