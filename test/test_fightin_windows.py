"""Run from the repo root: python -m pytest test/"""
import re

from src.fightin.windows import BREAK, windows

EN = ' '.join(f'w{k}' for k in range(100))


def test_english_window_and_merge():
    text = EN.replace('w50', 'Anthropic')
    assert windows(text, re.compile('anthropic', re.I), 'en', 2) == 'w48 w49 Anthropic w51 w52'
    text = EN.replace('w10', 'Anthropic').replace('w12', 'Claude').replace('w90', 'Anthropic')
    got = windows(text, re.compile('Anthropic|Claude'), 'en', 1)
    assert got == f'w9 Anthropic w11 Claude w13{BREAK}w89 Anthropic w91'


def test_chinese_window_and_no_match():
    text = '今天天气很好。Anthropic发布了新模型，引发广泛关注。另外一些无关的内容在这里。'
    got = windows(text, re.compile('Anthropic'), 'zh', 3)
    assert 'Anthropic' in got and '无关' not in got
    assert windows('没有提到', re.compile('Anthropic'), 'zh', 3) == ''
