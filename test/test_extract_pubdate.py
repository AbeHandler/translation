"""Run from the repo root: python -m pytest test/"""
from src.extract_pubdate import extract_pubdate

JSON_LD_PAGE = '''<html><head><script type="application/ld+json">
{"@context": "https://schema.org", "@type": "NewsArticle", "datePublished": "2026-09-11T15:52:23+08:00"}
</script></head><body><p>text</p></body></html>'''

# zhidx.com style: the date is only in a visible byline
BYLINE_PAGE = '''<html><head><title>t</title></head><body>
<div class="info"><span class="time">2026/09/16 </span></div><p>article text</p></body></html>'''

# leiphone.com style: a byline that only the extensive search finds
TABLE_BYLINE_PAGE = '''<html><head><title>t</title></head><body>
<table><tr><td class="author">someone</td><td class="time">2021-09-06 11:58</td></tr></table>
<p>article text</p></body></html>'''

NO_DATE_PAGE = '<html><head><title>t</title></head><body><p>no date here</p></body></html>'


def test_newspaper_gives_full_timestamp_from_json_ld():
    assert extract_pubdate(JSON_LD_PAGE, 'https://example.com/a') == ('2026-09-11T15:52:23+08:00', 'newspaper')


def test_htmldate_finds_byline_date():
    assert extract_pubdate(BYLINE_PAGE, 'https://example.com/p/594440.html') == ('2026-09-16', 'htmldate')


def test_extensive_search_is_last_resort():
    url = 'https://example.com/category/academic/b.html'
    assert extract_pubdate(TABLE_BYLINE_PAGE, url) == ('2021-09-06', 'htmldate_extensive')


def test_no_date():
    assert extract_pubdate(NO_DATE_PAGE, 'https://example.com/p/1.html') == (None, None)
