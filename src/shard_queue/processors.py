"""Row processors for scripts/process_queue.py (-processor name). Each takes a row (dict) and returns a dict of
new fields. Add one here for each use."""
import httpx

HEADERS = {'User-Agent': 'Mozilla/5.0 (research crawler; abha4861@colorado.edu)'}


def domain(row):
    """The URL's host; no network. For testing a queue end to end."""
    from urllib.parse import urlparse
    return {'domain': urlparse(row['url']).hostname}


def fetch_status(row):
    """HTTP status, final URL (after redirects) and content type of row['url']."""
    response = httpx.get(row['url'], headers=HEADERS, follow_redirects=True, timeout=30)
    return {'status': response.status_code, 'final_url': str(response.url),
            'content_type': response.headers.get('content-type', '')}


PROCESSORS = {'domain': domain, 'fetch_status': fetch_status}
