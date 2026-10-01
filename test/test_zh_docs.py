"""Run from the repo root: python -m pytest test/"""
import gzip

from src.link_language.fetch import RawPage
from src.zh_docs import ZhDocFetcher, is_homepage

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
