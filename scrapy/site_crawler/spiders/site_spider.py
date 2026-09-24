"""
One generic spider for any site: `-a domain=denverpost.com` crawls that domain (and its subdomains),
writing one item per HTML page with the page's outgoing links.

    cd scrapy && scrapy crawl site -a domain=denverpost.com -o pages.jsonl -s CLOSESPIDER_PAGECOUNT=20
"""
import datetime

import scrapy
from scrapy.http import TextResponse


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
        yield {
            'url': response.url,
            'title': response.css('title::text').get(default='').strip(),
            'links': links,
            'crawled_at': datetime.datetime.now(datetime.timezone.utc).isoformat(),
        }
        for link in links:
            yield response.follow(link, self.parse)  # OffsiteMiddleware drops other domains


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
