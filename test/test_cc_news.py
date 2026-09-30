"""Run from the repo root: python -m pytest test/"""
import datetime
import json

import pyarrow as pa
import pyarrow.parquet as pq
import pytest

from src.cc_news import ArticleHtmlArchiver, ArticleLinkExtractor, grep_links, match_seed_links, warc_files

ARTICLE = ('<html><head><title>AI 新闻</title></head><body><nav><a href="/home">首页</a></nav><article>'
           + '<p>这是一篇关于人工智能的长文章，讨论了前沿模型的发展节奏和安全问题。' * 10
           + '<a href="https://darioamodei.com/post/we-must-pace-the-frontier">长文</a></p>'
           + '</article><footer><a href="/about">关于</a></footer></body></html>').encode('utf-8')


def write_html(path, pages):
    rows = [{'url': url, 'language': 'zh', 'warc_date': '2026-09-23T00:00:00Z', 'content_type': 'text/html',
             'record_id': f'<urn:uuid:{i}>', 'html': html} for i, (url, html) in enumerate(pages)]
    pq.write_table(pa.Table.from_pylist(rows, ArticleHtmlArchiver.SCHEMA), path)


def test_links_come_from_the_article_body_of_the_saved_html(tmp_path):
    write_html(tmp_path / 'w.parquet', [('https://a.cn/1', ARTICLE), ('https://a.cn/2', b'')])
    extractor = ArticleLinkExtractor()
    info = extractor.write(str(tmp_path / 'w.parquet'), str(tmp_path / 'w.jsonl'))
    rows = [json.loads(line) for line in open(tmp_path / 'w.jsonl', encoding='utf-8')]
    assert info['rows'] == 1 and info['errors'] == 1
    assert [link['href'] for link in rows[0]['links']] == ['https://darioamodei.com/post/we-must-pace-the-frontier']
    assert rows[0]['record_id'] == '<urn:uuid:0>' and rows[0]['language'] == 'zh'


def test_grep_finds_encoded_redirect_links(tmp_path):
    rows = [{'url': 'u1', 'title': 't', 'language': 'zh', 'links': [
                {'href': 'https://link.zhihu.com/?target=https%3A%2F%2Fdarioamodei.com%2Fpost%2F'
                         'we-must-pace-the-frontier', 'text': 'x'},
                {'href': 'https://openai.com/index/foo', 'text': 'y'}]},
            {'url': 'u2', 'title': 't', 'language': 'en', 'links': [{'href': 'https://example.com', 'text': 'z'}]}]
    (tmp_path / 'l.jsonl').write_text(''.join(json.dumps(r) + '\n' for r in rows), encoding='utf-8')
    matches = list(grep_links([str(tmp_path / 'l.jsonl')],
                              ['darioamodei.com/post/we-must-pace-the-frontier', 'openai.com/index/']))
    assert [(m['pattern'], m['decoded']) for m in matches] == [
        ('darioamodei.com/post/we-must-pace-the-frontier', True), ('openai.com/index/', False)]


def test_match_refuses_an_incomplete_range_unless_partial(tmp_path):
    (tmp_path / 'a.jsonl').write_text('', encoding='utf-8')
    keys, links_path = ['a', 'b'], (lambda key: str(tmp_path / f'{key}.jsonl'))
    with pytest.raises(FileNotFoundError, match='1 of 2 WARCs'):
        match_seed_links(keys, links_path, ['x.com/'], str(tmp_path / 'm.jsonl'))
    assert match_seed_links(keys, links_path, ['x.com/'], str(tmp_path / 'm.jsonl'), partial=True) == {}


def test_warc_files_by_date_and_test_suffix(tmp_path):
    for name in ('CC-NEWS-20260922000000-00001', 'CC-NEWS-20260923000000-00002',
                 'CC-NEWS-20260923000000-00003.max100'):
        (tmp_path / f'{name}.parquet').write_bytes(b'')
    day = datetime.date(2026, 9, 23)
    assert [p.split('/')[-1] for p in warc_files(str(tmp_path), '.parquet', day, day)] == [
        'CC-NEWS-20260923000000-00002.parquet']
    assert [p.split('/')[-1] for p in warc_files(str(tmp_path), '.parquet', day, day, max_n=100)] == [
        'CC-NEWS-20260923000000-00003.max100.parquet']


def test_ai_article_links_joins_html_and_links_and_keeps_external_links(tmp_path):
    from src.cc_news import ai_article_links
    write_html(tmp_path / 'w.parquet', [('https://a.cn/1', b'<html><body><p>New AI rules. AI chips.</p></body></html>'),
                                        ('https://a.cn/2', b'<html><body><p>Football.</p></body></html>')])
    links = [{'url': 'https://a.cn/1', 'record_id': '<urn:uuid:0>', 'language': 'zh', 'links': [
                 {'href': 'https://x.com/a', 'text': '', 'internal': False},
                 {'href': 'https://a.cn/other', 'text': '', 'internal': True},
                 {'href': 'https://x.com/a', 'text': '', 'internal': False}]},
             {'url': 'https://a.cn/2', 'record_id': '<urn:uuid:1>', 'links': [{'href': 'https://y.com', 'text': '',
                                                                              'internal': False}]}]
    (tmp_path / 'w.jsonl').write_text(''.join(json.dumps(r) + '\n' for r in links), encoding='utf-8')
    rows = list(ai_article_links(str(tmp_path / 'w.parquet'), str(tmp_path / 'w.jsonl')))
    assert rows == [{'srcpage': 'https://a.cn/1', 'src_language': 'zh', 'url': 'https://x.com/a'}]
    assert len(list(ai_article_links(str(tmp_path / 'w.parquet'), str(tmp_path / 'w.jsonl'), 3))) == 0


def test_links_rows_record_ai_mentions_and_the_queue_uses_them(tmp_path):
    from src.cc_news import ai_article_links
    write_html(tmp_path / 'w.parquet', [('https://a.cn/1', ARTICLE.replace(b'</article>', b'<p>AI AI</p></article>'))])
    ArticleLinkExtractor().write(str(tmp_path / 'w.parquet'), str(tmp_path / 'w.jsonl'))
    (row,) = [json.loads(line) for line in open(tmp_path / 'w.jsonl', encoding='utf-8')]
    assert row['ai_mentions'] == 2
    assert [r['url'] for r in ai_article_links('no-html-needed', str(tmp_path / 'w.jsonl'))] == [
        'https://darioamodei.com/post/we-must-pace-the-frontier']
