"""Run from the repo root: python -m pytest test/"""
from src.seed_documents import is_primary, source_kind


def test_primary_sources_are_not_news_and_are_single_documents():
    outlets = {'cnbc.com'}
    assert is_primary('anthropic.com/news/statement-department-of-war', outlets)
    assert is_primary('x.com/sama/status/1790075827666796666', outlets)
    assert is_primary('truthsocial.com/@realDonaldTrump/posts/112984762512136574', outlets)
    assert not is_primary('x.com/jakecoyleAP', outlets)                       # a profile, not a post
    assert not is_primary('cnbc.com/2025/01/27/deepseek', outlets)            # a corpus outlet
    assert not is_primary('bloomberg.com/news/articles/2024-02-27/apple', outlets)   # a major outlet
    assert not is_primary('amazon.com/gp/product/B0BLS3Y632', outlets)        # an affiliate link
    memo = 'washingtonpost.com/documents/67a7081c-c770-4f05-a39e-9d02117e50e8.pdf'   # a source the Post hosts
    assert is_primary(memo, outlets) and source_kind(memo) == 'hosted document'
    assert is_primary('documentcloud.org/documents/24241000-2023-12-27-nyt-dkt-1-complaint', outlets)
    assert is_primary('cac.gov.cn/2023-04/11/c_1682854275475410.htm', outlets)
    assert source_kind('cac.gov.cn/2023-04/11/c_1682854275475410.htm') == 'government'


def test_kinds_of_source():
    assert source_kind('x.com/sama/status/1') == 'social post'
    assert source_kind('storage.courtlistener.com/recap/gov.uscourts.dcd.223205/x.pdf') == 'court or legal'
    assert source_kind('media.defense.gov/2026/Jun/08/x.pdf') == 'government'
    assert source_kind('metr.org/blog/2026-08-26-incident') == 'research'
    assert source_kind('blog.youtube/inside-youtube/a-personal-update-from-susan') == 'organisation'


def test_primary_sources_are_ranked_by_outlets_linking_soon_after_the_first_link():
    from src.primary_sources import link_rows, primary_sources
    statement = 'https://www.anthropic.com/news/statement-department-of-war'
    rows = []
    for i in range(5):                                           # 5 outlets in two days
        day = f'2026-02-2{7 + i % 2}'
        rows += link_rows(f'https://news{i}.com/a', [statement, 'https://www.cnbc.com/x'], day, 'en')
    rows += link_rows('https://late.com/a', [statement], '2026-06-01', 'en')     # months later
    rows += link_rows('https://www.cnbc.com/x', [], '2026-02-27', 'en')            # cnbc is an outlet, so news
    (found,) = primary_sources(rows, {r['outlet'] for r in rows} | {'cnbc.com'})
    assert found['document'] == 'anthropic.com/news/statement-department-of-war'
    assert (found['outlets_first'], found['outlets'], found['first_seen']) == (5, 6, '2026-02-27')
