"""Run from the repo root: python -m pytest test/"""
import json

from src.en_zh_links import chinese_title, fetch_failed, line_url, source_titles


def test_failed_fetches_and_chinese_titles():
    assert fetch_failed({'label_source': 'fetched', 'status': 404})
    assert not fetch_failed({'label_source': 'fetched', 'status': 200})
    assert not fetch_failed({'label_source': 'host_cache'})
    assert chinese_title('AI大模型价格战再起：字节跳动下调豆包价格')
    assert not chinese_title("Liu Chien-ping (劉千萍): Taiwan's Gen Z women in public life")
    assert not chinese_title(None)


def test_source_titles_reads_only_the_wanted_articles(tmp_path):
    rows = [{'url': 'https://a.com/1', 'title': 'One', 'links': []},
            {'url': 'https://a.com/q?x=中', 'title': '中文标题', 'links': []},
            {'url': 'https://b.com/2', 'title': 'Two', 'links': []}]
    path = tmp_path / 'w.jsonl'
    path.write_text(''.join(json.dumps(r) + '\n' for r in rows), encoding='utf-8')
    assert line_url(json.dumps(rows[1]) + '\n') == 'https://a.com/q?x=中'
    assert source_titles([str(path)], {'https://a.com/1', 'https://a.com/q?x=中'}) == {
        'https://a.com/1': 'One', 'https://a.com/q?x=中': '中文标题'}
