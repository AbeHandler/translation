"""Listing the regular Common Crawl: crawl ids from index.commoncrawl.org, and each crawl's warc.paths.gz."""
import gzip
import json
import os
import urllib.request

CRAWLS_URL = 'https://index.commoncrawl.org/collinfo.json'
DATA_URL = 'https://data.commoncrawl.org/'
TIMEOUT = 120


def crawls_since(year):
    """Ids of the main crawls (CC-MAIN-YYYY-WW) from that year on, oldest first."""
    with urllib.request.urlopen(CRAWLS_URL, timeout=TIMEOUT) as response:
        ids = [crawl['id'] for crawl in json.load(response)]
    return sorted(i for i in ids if i.startswith('CC-MAIN-') and i >= f'CC-MAIN-{year}')


def warc_paths(crawl):
    """The crawl's WARC paths (crawl-data/<crawl>/segments/.../warc/....warc.gz)."""
    with urllib.request.urlopen(f'{DATA_URL}crawl-data/{crawl}/warc.paths.gz', timeout=TIMEOUT) as response:
        return gzip.decompress(response.read()).decode().split()


def write_warc_list(path, year):
    """Write every WARC path of every crawl since year to path, one per line (via .part), unless it exists.
    Returns the number of paths in the file."""
    if not os.path.exists(path):
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path + '.part', 'w') as f:
            for crawl in crawls_since(year):
                f.write('\n'.join(warc_paths(crawl)) + '\n')
        os.rename(path + '.part', path)
    with open(path) as f:
        return sum(1 for line in f if line.strip())
