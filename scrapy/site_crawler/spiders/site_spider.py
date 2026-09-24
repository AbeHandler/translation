"""
One generic spider for any site: `-a domain=denverpost.com` crawls that domain (and its subdomains),
writing one item per HTML page with the page's outgoing links and publication date to pages.jsonl, and its
raw HTML to Parquet (site_crawler/pipelines.py).

PYTHONPATH=.. so `src` (at the repo root) imports:
    cd scrapy && PYTHONPATH=.. scrapy crawl site -a domain=denverpost.com -o pages.jsonl -s HTML_DIR=html \
        -s CLOSESPIDER_PAGECOUNT=20
"""
import datetime

import scrapy
from scrapy.http import HtmlResponse, TextResponse

from src.extract_pubdate import extract_pubdate


class SiteSpider(scrapy.Spider):
    name = 'site'

    def __init__(self, domain, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if any(c in domain for c in '/: '):
            raise ValueError(f'domain must be bare, e.g. denverpost.com, not {domain!r}')
        self.allowed_domains = [domain]
        # Both, because many sites only resolve at one of them (e.g. huxiu.com has no DNS, www.huxiu.com does).
        self.start_urls = [f'https://{domain}/', f'https://www.{domain}/']

    async def start(self):
        # Deduplicated (unlike the default start), so homepages aren't refetched via their own links or on resume.
        for url in self.start_urls:
            yield scrapy.Request(url, self.parse)

    def parse(self, response):
        if not isinstance(response, TextResponse):  # images, PDFs, ...
            return
        links = absolute_links(response)
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
        for link in links:
            yield response.follow(link, self.parse)  # OffsiteMiddleware drops other domains

    def pubdate_of(self, response):
        """Logged as an ERROR (counted in the crawl stats) rather than raised, so one odd page can't stop a crawl."""
        try:
            return extract_pubdate(response.text, response.url)
        except Exception:
            self.logger.exception(f'pubdate extraction failed for {response.url}')
            return None, None


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
