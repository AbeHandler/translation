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


def test_a_storm_hits_and_subsides_a_year_long_template_stream_is_not_one():
    articles, cluster_of = [], {}
    for o in range(6):
        for d in range(200):                             # a daily price notice for 200 days: 3.5% in any week
            date = shift('2024-01-01', d)
            for k in range(20):
                url = f'o{o}-{d}-{k}'
                articles.append({'url': url, 'outlet': f'outlet{o}.com', 'date': date})
                if k == 0:
                    cluster_of[url] = 'prices'
    assert storms(articles, cluster_of) == []
    assert storms(articles, cluster_of, min_peak_share=0) != []


def test_seeds_are_the_documents_a_storm_cites_not_generic_links():
    from src.media_storms import document_key, storm_seeds
    assert document_key('https://www.ai.meta.com/blog/llama/?utm=x#top') == 'ai.meta.com/blog/llama'
    assert document_key('https://twitter.com/') is None
    assert document_key('https://apnews.com/hub/hollywood-strikes/') is None
    assert document_key('https://www.facebook.com/sharer/sharer.php?u=x') is None
    blog = 'https://ai.meta.com/blog/large-language-model-llama-meta-ai/'
    members = {'llama': [f'https://n{i}.com/a' for i in range(10)]}
    links_of = {f'https://n{i}.com/a': ([blog] if i < 6 else []) + ['https://twitter.com/x'] for i in range(10)}
    for k in range(6):                                   # twitter.com/x is cited in 7 storms: generic
        members[f's{k}'] = [f'https://m{k}.com/a']
        links_of[f'https://m{k}.com/a'] = ['https://twitter.com/x']
    found = storm_seeds(members, links_of)
    assert found['llama']['seeds'][0]['href'] == blog and found['llama']['seed_share'] == 0.6
    assert len(found['llama']['citing']) == 6 and found['s0']['seed_share'] == 0.0
    assert not found['llama']['template']
    stock_page = 'https://www.marketbeat.com/stocks/NASDAQ/X/'
    notices = storm_seeds({'n': ['https://a.com/1']}, {'https://a.com/1': [stock_page]})
    assert notices['n']['template']


def test_a_crawled_page_counts_if_chinese_about_ai_and_dated():
    from src.media_storms import site_crawl_page
    html = ('<html><head><title>DeepSeek发布新模型</title></head><body><p>人工智能公司DeepSeek发布大模型。</p>'
            '<a href="https://api-docs.deepseek.com/news/r1">公告</a></body></html>')
    row = {'url': 'https://www.thepaper.cn/a1', 'language': 'zh', 'html': html.encode()}
    outcome, (date, day_row, links) = site_crawl_page(row, '2026-10-04', pubdate=lambda h, u: '2025-01-20T08:00:00')
    assert outcome == 'kept'
    assert date == '2025-01-20' and day_row == {'url': row['url'], 'outlet': 'thepaper.cn', 'title': 'DeepSeek发布新模型'}
    assert {'href': 'https://api-docs.deepseek.com/news/r1'} in links
    assert site_crawl_page(row, '2026-10-04', pubdate=lambda h, u: '2019-05-01') == ('date out of range', None)
    assert site_crawl_page(row, '2026-10-04', pubdate=lambda h, u: None) == ('no date', None)
    mislabelled = {**row, 'language': 'en'}                  # the title decides, not the recorded language
    assert site_crawl_page(mislabelled, '2026-10-04', pubdate=lambda h, u: '2025-01-20')[0] == 'kept'
    english = {**row, 'language': 'zh', 'html': html.replace('DeepSeek发布新模型', 'DeepSeek releases R1').encode()}
    assert site_crawl_page(english, '2026-10-04', pubdate=lambda h, u: '2025-01-20')[0] == 'not chinese'
    weather = {**row, 'html': '<html><title>北京今日天气预报</title><p>今天天气很好。</p></html>'.encode()}
    assert site_crawl_page(weather, '2026-10-04', pubdate=lambda h, u: '2025-01-20')[0] == 'not about ai'
