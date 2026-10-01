"""Run from the repo root: python -m pytest test/"""
import gzip

from src.link_language.fetch import RawPage
from src.zh_docs import ZhDocFetcher, doc_date, is_homepage, page_title

ARTICLE = ('<html><head><title>外交部发言人答记者问</title></head><body><nav>首页 新闻 外交部</nav><article>'
           + ''.join(f'<p>第{i}段：中方一贯主张通过对话协商和平解决争端，愿同各方一道维护地区和平稳定与发展繁荣。</p>'
                     for i in range(12)) + '</article></body></html>')


def fake_fetch(pages):
    return lambda url, client: RawPage(200, url, 'text/html', pages[url])


def test_an_article_is_a_document_and_its_html_is_kept(tmp_path):
    fetcher = ZhDocFetcher(str(tmp_path), fetch=fake_fetch({'https://www.mfa.gov.cn/fyrbt/202609/t1.shtml': ARTICLE}))
    doc = fetcher.doc({'url': 'https://www.mfa.gov.cn/fyrbt/202609/t1.shtml'})
    assert doc['is_document'] and doc['title'] == '外交部发言人答记者问' and doc['n_han'] > 200
    assert '和平解决争端' in doc['text'] and '首页 新闻' not in doc['text']
    with gzip.open(fetcher.html_path('https://www.mfa.gov.cn/fyrbt/202609/t1.shtml'), 'rt', encoding='utf-8') as f:
        assert f.read() == ARTICLE


def test_homepages_and_short_pages_are_not_documents(tmp_path):
    pages = {'https://www.deepseek.com/': ARTICLE, 'https://x.cn/a/1': '<html><body><p>页面不存在</p></body></html>',
             'https://x.cn/a/2': ARTICLE.replace('外交部发言人答记者问', '系统维护_中华人民共和国外交部')}
    fetcher = ZhDocFetcher(str(tmp_path), fetch=fake_fetch(pages))
    assert not fetcher.doc({'url': 'https://www.deepseek.com/'})['is_document']
    assert not fetcher.doc({'url': 'https://x.cn/a/1'})['is_document']
    assert not fetcher.doc({'url': 'https://x.cn/a/2'})['is_document']  # an error page answering 200
    assert is_homepage('http://www.taop.com') and not is_homepage('https://x.cn/?p=88838')


def test_document_titles_and_dates():
    assert page_title('<html><head><title></title><meta property="og:title" content="甘肃公安侦破首例AI虚假信息案">'
                      '</head><body><h1>x</h1></body></html>') == '甘肃公安侦破首例AI虚假信息案'
    assert page_title('<html><head><title>外交部长活动_中华人民共和国外交部</title></head>'
                      '<body><h1>秦刚：安全是世界各国的权利</h1></body></html>') == '秦刚：安全是世界各国的权利'
    assert page_title('<html><head><title>生成式人工智能服务管理暂行办法_中央网络安全和信息化委员会办公室</title>'
                      '</head><body></body></html>') == '生成式人工智能服务管理暂行办法'
    assert doc_date('', 'https://www.cac.gov.cn/2023-07/13/c_1690898.htm', '2024-01-01') == ('2023-07-13', 'url')
    assert doc_date('', 'https://www.fmprc.gov.cn/wjbzhd/202302/t20230221_11028.shtml', None) == ('2023-02-21', 'url')
    assert doc_date("var x; create_time: '2023-05-07 10:11'", 'https://mp.weixin.qq.com/s/abc', '2024-10-15') == (
        '2023-05-07', 'wechat')
    assert doc_date('', 'https://www.miit.gov.cn/zwgk/art/2023/art_48fe.html', '2024-08-16 17:24') == (None, None)
    assert doc_date('', 'https://x.cn/a/1', '2024-08-16T17:24:00') == ('2024-08-16', 'html')
