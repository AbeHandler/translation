"""LinkLanguageLabeler: a shard-queue row processor ({url, ...} -> language fields) with a host cache shared by
every worker through files: <cache_dir>/<host>.jsonl, one line per page of that host fetched and labelled. Once
the first HOST_SAMPLE labels of a host agree, further links to it are labelled from the cache without fetching.
Workers may race to write a host's first lines; that only means a few extra fetches."""
import json
import os
from urllib.parse import urlparse

import httpx

from src.link_language.fetch import fetch_page
from src.link_language.script import label_text

HOST_SAMPLE = 3


class LinkLanguageLabeler:
    def __init__(self, cache_dir, fetch=fetch_page):
        self.cache_dir = cache_dir
        self.fetch = fetch  # (url, client) -> Page
        self.client = httpx.Client()
        os.makedirs(cache_dir, exist_ok=True)

    def cache_path(self, host):
        return os.path.join(self.cache_dir, (host or 'nohost').replace('/', '_') + '.jsonl')

    def host_language(self, host):
        """The host's language, if its first HOST_SAMPLE fetched pages all got the same (known) label."""
        path = self.cache_path(host)
        if not os.path.exists(path):
            return None
        with open(path, encoding='utf-8') as f:
            labels = [json.loads(line)['language'] for line in f if line.strip()][:HOST_SAMPLE]
        if len(labels) == HOST_SAMPLE and len(set(labels)) == 1 and labels[0] != 'unknown':
            return labels[0]
        return None

    def remember(self, host, url, language):
        with open(self.cache_path(host), 'a', encoding='utf-8') as f:  # one short line: an atomic append
            f.write(json.dumps({'url': url, 'language': language}) + '\n')

    def label(self, row):
        """{host, language, label_source, ...}: from the host cache, or by fetching (status, final_url,
        content_type, title, han_share, method). A fetch that fails raises, and the queue records the error."""
        host = urlparse(row['url']).hostname
        cached = self.host_language(host)
        if cached:
            return {'host': host, 'language': cached, 'label_source': 'host_cache'}
        page = self.fetch(row['url'], self.client)
        language, han_share, method = label_text(page.text) if page.text else ('unknown', 0.0, 'no_text')
        if page.status < 400 and page.text:
            self.remember(host, row['url'], language)
        return {'host': host, 'language': language, 'label_source': 'fetched', 'status': page.status,
                'final_url': page.final_url, 'content_type': page.content_type, 'title': page.title[:300],
                'han_share': round(han_share, 3), 'method': method}
