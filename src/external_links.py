"""Which links of a page point outside its site: another registered domain (so a site's own subdomains and CDNs
don't count), and not an image or media file. Shared by the CC-NEWS and regular Common Crawl link queues."""
import re
from urllib.parse import urlparse

import tldextract

# offline: the public suffix list bundled with tldextract, never fetched
_domains = tldextract.TLDExtract(suffix_list_urls=())
MEDIA = re.compile(r'\.(jpe?g|png|gif|webp|svg|bmp|ico|mp4|mp3|m4a|mov|webm|avif)$', re.I)


def registered_domain(url):
    """xinhuanet.com for https://www.news.xinhuanet.com/a."""
    return _domains(url).top_domain_under_public_suffix or urlparse(url).hostname


def external_links(page_url, hrefs):
    """The hrefs (unique, in order) that leave page_url's site and aren't images or media."""
    site = registered_domain(page_url)
    return [href for href in dict.fromkeys(hrefs)
            if registered_domain(href) != site and not MEDIA.search(urlparse(href).path)]
