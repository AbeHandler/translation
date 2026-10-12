"""Run from the repo root: python -m pytest test/"""
import datetime

from src.crawl_ids import IdProber, id_of, urls_for


def test_urls_and_ids():
    assert urls_for('ithome.com', 978957) == ['https://www.ithome.com/0/978/957.htm']
    assert id_of('ithome.com', 'https://www.ithome.com/0/978/957.htm') == 978957
    assert id_of('yicai.com', 'https://www.yicai.com/brief/103287793.html') == 103287793
    assert len(urls_for('yicai.com', 5)) == 2 and id_of('jiemian.com', 'https://x.com/a') is None


def fake_site(first=1000, last=5000, per_day=100, gap=5):
    """IDs first..last, every gap-th missing; ID k published first_day + (k - first) // per_day."""
    day0 = datetime.date(2026, 7, 1)

    def fetch(url):
        k = id_of('jiemian.com', url)
        if k is None or not first <= k <= last or k % gap == 0:
            return 404, ''
        return 200, str(day0 + datetime.timedelta(days=(k - first) // per_day))
    return fetch, (lambda html, url: html)


def test_binary_searches():
    fetch, date_of = fake_site()
    prober = IdProber('jiemian.com', fetch, date_of)
    assert 5000 - prober.window <= prober.latest(1500) <= 5000
    first = prober.first_on_or_after('2026-07-11', 1000, 5000)      # day 10: IDs from 2000
    assert 2000 - prober.window <= first <= 2000 + 1
    assert len(prober.cache) < 200                                   # a few dozen probes, not a scan


def test_sparse_ids():
    """jiemian-like: 1 ID in 40 is an article; consecutive probes alone miss them."""
    fetch, date_of = fake_site(first=100_000, last=500_000, per_day=4000, gap=10**9)
    sparse = lambda url: fetch(url) if id_of('jiemian.com', url) % 40 == 0 else (404, '')   # noqa: E731
    prober = IdProber('jiemian.com', sparse, date_of)
    first = prober.first_on_or_after('2026-07-11', 100_000, 500_000)    # day 10: IDs from 140000
    assert 140_000 - 400 <= first <= 140_000 + 40          # a little early is harmless: a few extra URLs


def test_page_date():
    from src.crawl_ids import page_date
    assert page_date('', '2026-07-21T10:00') == '2026-07-21'
    assert page_date('<div publish-time="1784601986">', None) == '2026-07-21'
    assert page_date('发布于2026年7月3日', None) == '2026-07-03' and page_date('x', None) is None
