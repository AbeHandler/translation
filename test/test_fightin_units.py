"""Run from the repo root: python -m pytest test/"""
from src.fightin.units import parse_ns, units

STOP = frozenset({'the', 'of', 'a'})


def test_words_keep_only_each_languages_own_script():
    assert units(['The', 'AI', 'model', '人工智能', ',', '2025'], 'en') == ['the', 'ai', 'model']
    # Chinese pages: lowercase Latin words are quoted English; names and acronyms count
    assert units(['OpenAI', '发布', 'new', '模型', 'GPT-5'], 'zh') == ['openai', '发布', '模型', 'gpt-5']


def test_english_phrases_have_content_words_at_both_ends_and_never_cross_breaks():
    toks = ['the', 'Department', 'of', 'War', 'said', ',', 'AI', 'safety']
    assert set(units(toks, 'en', (2, 3), STOP)) == {'war said', 'ai safety', 'department of war'}
    assert units(['a', 'b', 'model'], 'en', (2,), STOP) == []      # one-letter words aren't edges


def test_chinese_phrases():
    toks = ['人工智能', '的', '发展', '，', 'OpenAI', 'GPT-5', '发布']
    got = units(toks, 'zh', (2, 3))
    assert '人工智能的发展' in got and 'openai gpt-5' in got and 'gpt-5发布' in got
    assert not any(g.startswith('的') or g.endswith('的') for g in got)
    assert not any('，' in g for g in got)


def test_parse_ns():
    assert parse_ns('1') == (1,) and parse_ns('2-3') == (2, 3)
