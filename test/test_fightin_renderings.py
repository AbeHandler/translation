"""Run from the repo root: python -m pytest test/"""
from src.fightin.renderings import KnownRenderings
from src.fightin.units import units
from src.dispersion.tokens import tokens


def test_longest_name_first_and_counted_as_a_name():
    r = KnownRenderings([('文心', 'ERNIE'), ('文心一言', 'ERNIE Bot'), ('百度', 'Baidu')])
    text = r.apply('百度发布文心一言，文心大模型升级')
    assert text == ' Baidu 发布 ERNIE Bot ， ERNIE 大模型升级'
    found = units([t for t, _, _ in tokens(text, 'zh')], 'zh', (2, 3))
    assert 'ernie bot' in found and 'baidu发布' in found


def test_reads_the_config():
    r = KnownRenderings.read('config/fightin_known_renderings.tsv')
    assert r.apply('通义千问').strip() == 'Qwen' and r.apply('千问').strip() == 'Qwen'
