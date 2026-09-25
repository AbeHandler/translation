"""Run from the repo root: python -m pytest test/  (the spider lives in scrapy/, so that goes on the path)"""
import gzip
import sys

from scrapy.http import Request, TextResponse, XmlResponse

sys.path.insert(0, 'scrapy')
from site_crawler.spiders.site_spider import SiteSpider  # noqa: E402

INDEX = b'''<?xml version="1.0"?><sitemapindex xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
<sitemap><loc>https://www.x.com/sitemap1.xml</loc></sitemap><sitemap><loc>https://www.x.com/sitemap1.xml</loc></sitemap>
</sitemapindex>'''
URLSET = b'''<?xml version="1.0"?><urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
<url><loc>https://x.com/article/old.html</loc><lastmod>2017-08-25</lastmod></url>
<url><loc>https://www.x.com/article/new.html</loc><lastmod>2026-09-13T10:00:00+08:00</lastmod></url>
</urlset>'''


class FakeStats:
    def inc_value(self, *args):
        pass


def spider():
    s = SiteSpider(domain='x.com')
    s.crawler = type('Crawler', (), {'stats': FakeStats()})()
    return s


def test_robots_sitemaps_and_index_are_followed_once():
    s = spider()
    body = b'User-agent: *\nSitemap: https://www.x.com/sitemap.xml\nSitemap:https://www.x.com/sitemap.xml\n'
    robots = TextResponse('https://www.x.com/robots.txt', body=body)
    assert [r.url for r in s.parse_robots(robots)] == ['https://www.x.com/sitemap.xml']
    index = XmlResponse('https://www.x.com/sitemap.xml', body=INDEX, request=Request('https://www.x.com/sitemap.xml'))
    assert [r.url for r in s.parse_sitemap(index)] == ['https://www.x.com/sitemap1.xml']


def test_sitemap_pages_newest_first_on_the_home_host_and_gzip_works():
    s = spider()
    s.home_host = 'www.x.com'
    for body, url in ((URLSET, 'https://www.x.com/s.xml'), (gzip.compress(URLSET), 'https://www.x.com/s.xml.gz')):
        requests = list(s.parse_sitemap(XmlResponse(url, body=body, request=Request(url))))
        assert [r.url for r in requests] == ['https://www.x.com/article/old.html', 'https://www.x.com/article/new.html']
        old, new = requests
        assert new.priority > old.priority and new.callback == s.parse


def test_usual_sitemap_paths_are_tried_and_a_non_sitemap_is_skipped():
    import asyncio
    s = spider()

    async def start_urls():
        return [r.url async for r in s.start()]
    urls = asyncio.run(start_urls())
    assert 'https://www.x.com/sitemap.xml' in urls and 'https://x.com/sitemap_index.xml' in urls
    homepage = TextResponse('https://www.x.com/sitemap.xml', body=b'<html><body>home</body></html>',
                            request=Request('https://www.x.com/sitemap.xml'))
    assert list(s.parse_sitemap(homepage)) == []
