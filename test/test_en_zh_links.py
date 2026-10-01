"""Run from the repo root: python -m pytest test/"""
import json

from src.en_zh_links import (body_ai_mentions, chinese_title, fetch_failed, is_press_release, line_url, slug_key,
                             source_info, story_ids, title_key)


def test_failed_fetches_and_chinese_titles():
    assert fetch_failed({'label_source': 'fetched', 'status': 404})
    assert not fetch_failed({'label_source': 'fetched', 'status': 200})
    assert not fetch_failed({'label_source': 'host_cache'})
    assert chinese_title('AI大模型价格战再起：字节跳动下调豆包价格')
    assert not chinese_title("Liu Chien-ping (劉千萍): Taiwan's Gen Z women in public life")
    assert not chinese_title(None)


def test_source_info_reads_only_the_wanted_articles(tmp_path):
    rows = [{'url': 'https://a.com/1', 'title': 'One', 'links': []},
            {'url': 'https://a.com/q?x=中', 'title': '中文标题', 'links': []},
            {'url': 'https://b.com/2', 'title': 'Two', 'links': []}]
    path = tmp_path / 'w.jsonl'
    path.write_text(''.join(json.dumps(r) + '\n' for r in rows), encoding='utf-8')
    assert line_url(json.dumps(rows[1]) + '\n') == 'https://a.com/q?x=中'
    info = source_info([str(path)], {'https://a.com/1', 'https://a.com/q?x=中'})
    assert {url: i['title'] for url, i in info.items()} == {'https://a.com/1': 'One', 'https://a.com/q?x=中': '中文标题'}
    assert info['https://a.com/1']['links_file'] == 'w.jsonl' and info['https://a.com/1']['body_ai_mentions'] is None


def test_body_ai_mentions_ignore_menus_and_sidebars(tmp_path):
    import pyarrow as pa
    import pyarrow.parquet as pq
    para = '<p>TSMC engineers allegedly shared photos of the 2nm process with a Japanese firm, prosecutors say.</p>'
    tsmc = f'<html><body><nav>AI | Gaming | Hardware</nav><article>{para * 8}</article></body></html>'
    ai = tsmc.replace('2nm process', '2nm process used for AI chips')
    pq.write_table(pa.table({'url': ['https://p.com/tsmc', 'https://p.com/ai'], 'html': [tsmc, ai]}),
                   tmp_path / 'w.parquet', row_group_size=1)
    assert body_ai_mentions(str(tmp_path / 'w.parquet'), {'https://p.com/tsmc', 'https://p.com/ai'}) == {
        'https://p.com/tsmc': 0, 'https://p.com/ai': 8}


def test_syndicated_copies_citing_the_same_url_are_one_story():
    zh = 'https://www.news.cn/20260923/0fc9/c.html'
    rows = [{'srcpage': 'https://www.wskg.org/npr-news/2026-09-23/trump-and-xi-meet-at-moment-of-global-consequence',
             'url': zh},
            {'srcpage': 'https://www.ksut.org/2026-09-23/trump-and-xi-meet-at-moment-of-global-consequence', 'url': zh},
            {'srcpage': 'https://a.com/news/12345', 'url': zh},
            {'srcpage': 'https://b.com/story/987', 'url': zh},
            {'srcpage': 'https://c.com/other', 'url': 'https://www.news.cn/other.html'}]
    titles = {'https://a.com/news/12345': 'Morning briefing - A News',
              'https://b.com/story/987': 'B | Morning briefing', 'https://c.com/other': 'Morning briefing'}
    ids = story_ids(rows, titles)
    assert ids[rows[0]['srcpage']] == ids[rows[1]['srcpage']]                # same slug
    assert ids['https://a.com/news/12345'] == ids['https://b.com/story/987']  # same title, same link
    assert ids['https://c.com/other'] != ids['https://a.com/news/12345']      # same title, different link
    assert ids[rows[0]['srcpage']] != ids['https://a.com/news/12345']
    assert title_key('Trump and Xi meet at moment of global consequence | WSKG') == (
        'trump and xi meet at moment of global consequence')
    assert slug_key('https://www.oeeee.com/html/202610/01/1748403.html') == ''


def test_press_releases_by_wire_site_or_wire_path():
    assert is_press_release('https://www.prnewswire.com/news-releases/chipmos-reports-302695386.html')
    assert is_press_release('https://en.acnnewswire.com/article.asp?art_id=105366')
    assert is_press_release('https://www.wsaz.com/prnewswire/2023/10/16/profet-ai-amplifies-international-presence/')
    assert not is_press_release('https://www.chinatalk.media/p/what-are-chinese-people-vibecoding')
    assert not is_press_release('https://www.wired.com/story/china-ai/')
