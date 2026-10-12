"""
Sites that number their articles (ithome /0/978/957.htm, jiemian /article/14800997.html ...): their article URLs
for a date window, by binary search over the IDs. A probe fetches an ID's page and reads its publication date; IDs
have gaps (deleted, unpublished, another section's numbers), so a probe tries the next few IDs until one is a live
article, then IDs further on in growing jumps (jiemian: most IDs are 404, and 快讯 pages carry their date only as an
epoch attribute: page_date). IDs grow with time (roughly), so the first ID on or after a date, and the latest
ID, are found in a few dozen probes. fetch: url -> (status, html), injected (requests on Alpine; a fake in tests).
"""
import datetime
import re

SITES = {   # URL templates per site (an ID may be any of them: yicai numbers news and briefs together)
    'ithome.com': ['https://www.ithome.com/0/{a}/{b:03d}.htm'],
    'jiemian.com': ['https://www.jiemian.com/article/{id}.html'],
    'yicai.com': ['https://www.yicai.com/news/{id}.html', 'https://www.yicai.com/brief/{id}.html'],
    'tmtpost.com': ['https://www.tmtpost.com/{id}.html', 'https://www.tmtpost.com/nictation/{id}.html'],
}
ID_IN_URL = {
    'ithome.com': re.compile(r'ithome\.com/0/(\d+)/(\d{3})\.htm'),
    'jiemian.com': re.compile(r'jiemian\.com/article/(\d+)\.html'),
    'yicai.com': re.compile(r'yicai\.com/(?:news|brief)/(\d+)\.html'),
    'tmtpost.com': re.compile(r'tmtpost\.com/(?:nictation/)?(\d{6,})\.html'),
}


EPOCH = re.compile(r'(?:publish|pub)[-_]?time\s*[=:]\s*["\']?(1\d{9})\b', re.I)
DATE = re.compile(r'(20\d\d)[-/年.](\d{1,2})[-/月.](\d{1,2})')


def page_date(html, extracted):
    """extracted (a date from src/extract_pubdate.py, or None), else an epoch publish-time attribute, else the
    first date written in the page."""
    if extracted:
        return extracted[:10]
    m = EPOCH.search(html)
    if m:
        return datetime.datetime.fromtimestamp(int(m.group(1)), datetime.timezone(datetime.timedelta(hours=8))) \
            .strftime('%Y-%m-%d')
    m = DATE.search(html)
    return f'{m.group(1)}-{int(m.group(2)):02d}-{int(m.group(3)):02d}' if m else None


def urls_for(site, article_id):
    return [t.format(id=article_id, a=article_id // 1000, b=article_id % 1000) for t in SITES[site]]


def id_of(site, url):
    """The article ID in a site's URL, or None."""
    m = ID_IN_URL[site].search(url)
    if not m:
        return None
    return int(m.group(1)) * 1000 + int(m.group(2)) if site == 'ithome.com' else int(m.group(1))


class IdProber:
    def __init__(self, site, fetch, date_of, window=8, max_jump=4096):
        """date_of: (html, url) -> 'YYYY-MM-DD' or None; window: consecutive IDs tried from a probed one, then jumps
        growing by 1.6 each up to max_jump (not powers of two, which can keep landing on the same dead residues)."""
        self.site, self.fetch, self.date_of, self.window = site, fetch, date_of, window
        self.offsets = list(range(window))
        while self.offsets[-1] * 1.6 <= max_jump:
            self.offsets.append(int(self.offsets[-1] * 1.6) + 1)
        self.cache = {}

    def probe(self, article_id):
        """(the first live ID found at or after article_id, its date), or None if all tried are dead."""
        for k in (article_id + d for d in self.offsets):
            if k not in self.cache:
                self.cache[k] = None
                for url in urls_for(self.site, k):
                    status, html = self.fetch(url)
                    date = self.date_of(html, url) if status == 200 and html else None
                    if date:
                        self.cache[k] = date[:10]
                        break
            if self.cache[k]:
                return k, self.cache[k]
        return None

    def latest(self, known, step=1000):
        """About the highest live ID: up in doubling steps from a known live ID until probes find nothing,
        then a binary search between the last live and the first dead probe."""
        lo, hi = known, None
        while hi is None:
            if self.probe(lo + step):
                lo += step
                step *= 2
            else:
                hi = lo + step
        while hi - lo > self.window:
            mid = (lo + hi) // 2
            lo, hi = (mid, hi) if self.probe(mid) else (lo, mid)
        return lo

    def first_on_or_after(self, date, lo, hi):
        """The lowest ID in [lo, hi] dated on or after date (binary search; dates grow with IDs)."""
        while hi - lo > self.window:
            mid = (lo + hi) // 2
            found = self.probe(mid)
            if found is None or found[1] >= date:   # nothing alive for max_jump IDs: past the newest
                hi = mid
            else:
                lo = min(found[0] + 1, hi)
        return lo
