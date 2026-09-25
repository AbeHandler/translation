"""
One generic spider for any site: `-a domain=denverpost.com` crawls that domain (and its subdomains),
writing one item per HTML page with the page's outgoing links and publication date to pages.jsonl, and its
raw HTML to Parquet (site_crawler/pipelines.py).

It finds pages two ways: by following links from the homepage, and from the sitemaps listed in the site's
robots.txt. Sitemaps matter: many news sites link only their newest articles from the homepage and load the
rest with JavaScript (e.g. 21jingji), which link-following never reaches. Sitemap pages are crawled newest
first (by lastmod), and the sitemaps are refetched every run, so each round picks up new articles.

PYTHONPATH=.. so `src` (at the repo root) imports:
    cd scrapy && PYTHONPATH=.. scrapy crawl site -a domain=denverpost.com -o pages.jsonl -s HTML_DIR=html \
        -s CLOSESPIDER_PAGECOUNT=20
"""
import datetime
from urllib.parse import urlparse

import scrapy
from scrapy.http import HtmlResponse, TextResponse, XmlResponse
from scrapy.utils.gz import gunzip, gzip_magic_number
from scrapy.utils.sitemap import Sitemap, sitemap_urls_from_robots

from src.extract_pubdate import extract_pubdate


SITEMAP_PRIORITY = 100_000  # above any page, so the sitemaps are read before the crawl gets going


class SiteSpider(scrapy.Spider):
    name = 'site'

    def __init__(self, domain, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if any(c in domain for c in '/: '):
            raise ValueError(f'domain must be bare, e.g. denverpost.com, not {domain!r}')
        self.allowed_domains = [domain]
        # Both, because many sites only resolve at one of them (e.g. huxiu.com has no DNS, www.huxiu.com does).
        self.start_urls = [f'https://{domain}/', f'https://www.{domain}/']
        # Many sites serve the same pages at both, so the crawl sticks to the first to answer with links (home_host):
        # links to the other are rewritten to it, so no page is crawled twice.
        self.host_pair = {domain, f'www.{domain}'}
        self.home_host = None
        self.sitemaps_seen = set()  # a sitemap index can list a sitemap twice, or itself

    async def start(self):
        # robots.txt and sitemaps first (SITEMAP_PRIORITY), and not deduplicated: refetched every run, so each
        # round sees the newest articles.
        for url in self.start_urls:
            yield scrapy.Request(url + 'robots.txt', self.parse_robots, dont_filter=True, priority=SITEMAP_PRIORITY)
        # Deduplicated (unlike the default start), so homepages aren't refetched via their own links or on resume.
        for url in self.start_urls:
            yield scrapy.Request(url, self.parse)

    def parse_robots(self, response):
        for url in sitemap_urls_from_robots(response.body, base_url=response.url):
            yield from self.sitemap_request(url)

    def sitemap_request(self, url):
        if url not in self.sitemaps_seen:
            self.sitemaps_seen.add(url)
            yield scrapy.Request(url, self.parse_sitemap, dont_filter=True, priority=SITEMAP_PRIORITY)

    def parse_sitemap(self, response):
        """A sitemap index: fetch its sitemaps. A sitemap: crawl its pages, newest first."""
        body = sitemap_body(response)
        if body is None:
            self.logger.error(f'not a sitemap: {response.url}')
            return
        sitemap = Sitemap(body)
        entries = list(sitemap)
        if sitemap.type == 'sitemapindex':
            for entry in entries:
                yield from self.sitemap_request(entry['loc'])
            return
        self.crawler.stats.inc_value('sitemap/pages', len(entries))
        for entry in entries:
            yield scrapy.Request(self.on_home_host(entry['loc']), self.parse,
                                 priority=recency_priority(entry.get('lastmod')))

    def parse(self, response):
        if not isinstance(response, TextResponse):  # images, PDFs, ...
            return
        links = absolute_links(response)
        host = urlparse(response.url).hostname
        if self.home_host is None and host in self.host_pair and links:  # huxiu.com answers with an empty page
            self.home_host = host
        elif response.meta.get('depth', 0) == 0 and host in self.host_pair and host != self.home_host:
            return  # the other start URL's homepage: a copy of home_host's
        pubdate, pubdate_source = self.pubdate_of(response)
        yield {
            'url': response.url,
            'title': response.css('title::text').get(default='').strip(),
            'pubdate': pubdate,
            'pubdate_source': pubdate_source,
            'links': links,
            'crawled_at': datetime.datetime.now(datetime.timezone.utc).isoformat(),
            # taken off again by HtmlParquetPipeline, so they aren't in pages.jsonl
            'content_type': response.headers.get('Content-Type', b'').decode('latin-1'),
            'html': response.body,
            'is_html': isinstance(response, HtmlResponse),
        }
        for link in links:  # links keeps the URLs as written; only what is followed is rewritten
            yield response.follow(self.on_home_host(link), self.parse)  # OffsiteMiddleware drops other domains

    def on_home_host(self, url):
        """https://www.x.com/a -> https://x.com/a when x.com is home_host (and vice versa); other URLs unchanged."""
        parsed = urlparse(url)
        if self.home_host and parsed.hostname in self.host_pair and parsed.hostname != self.home_host:
            return parsed._replace(netloc=parsed.netloc.replace(parsed.hostname, self.home_host, 1)).geturl()
        return url

    def pubdate_of(self, response):
        """Logged as an ERROR (counted in the crawl stats) rather than raised, so one odd page can't stop a crawl."""
        try:
            return extract_pubdate(response.text, response.url)
        except Exception:
            self.logger.exception(f'pubdate extraction failed for {response.url}')
            return None, None


def sitemap_body(response):
    """The sitemap XML in a response (gunzipped if need be), or None if it isn't one."""
    if gzip_magic_number(response):
        return gunzip(response.body)
    if isinstance(response, XmlResponse) or response.body.lstrip()[:200].lower().startswith(
            (b'<?xml', b'<urlset', b'<sitemapindex')):
        return response.body
    return None


def recency_priority(lastmod):
    """Scrapy fetches higher priorities first: minus the page's age in days, so the newest go first. 0 without
    a (parseable) lastmod."""
    try:
        age = (datetime.date.today() - datetime.date.fromisoformat((lastmod or '')[:10])).days
    except ValueError:
        return 0
    return -min(max(age, 0), 36500)


def absolute_links(response):
    """http(s) hrefs on the page, made absolute. Skips malformed ones (e.g. 'Invalid IPv6 URL')."""
    links = []
    for href in response.css('a::attr(href)').getall():
        try:
            url = response.urljoin(href.strip())
        except ValueError:
            continue
        if url.startswith(('http://', 'https://')):
            links.append(url)
    return links
