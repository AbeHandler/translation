"""
Sites that number their articles (ithome /0/978/957.htm, jiemian /article/14800997.html ...): their article URLs
for a date window, by binary search over the IDs. A probe fetches an ID's page and reads its publication date; IDs
have gaps (deleted, unpublished, another section's numbers), so a probe tries the next few IDs until one is a live
article. IDs grow with time (roughly), so the first ID on or after a date, and the latest ID, are found in a few
dozen probes. fetch: url -> (status, html), injected (requests on Alpine; a fake in tests).
"""
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


def urls_for(site, article_id):
    return [t.format(id=article_id, a=article_id // 1000, b=article_id % 1000) for t in SITES[site]]


def id_of(site, url):
    """The article ID in a site's URL, or None."""
    m = ID_IN_URL[site].search(url)
    if not m:
        return None
    return int(m.group(1)) * 1000 + int(m.group(2)) if site == 'ithome.com' else int(m.group(1))


class IdProber:
    def __init__(self, site, fetch, date_of, window=8):
        """date_of: (html, url) -> 'YYYY-MM-DD' or None; window: IDs tried after a probed one."""
        self.site, self.fetch, self.date_of, self.window = site, fetch, date_of, window
        self.cache = {}

    def probe(self, article_id):
        """(the first live ID at or after article_id within the window, its date), or None."""
        for k in range(article_id, article_id + self.window):
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
            if found is None or found[1] >= date:
                hi = mid
            else:
                lo = found[0] + 1
        return lo
