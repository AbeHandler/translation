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


def test_kinds_of_source():
    assert source_kind('x.com/sama/status/1') == 'social post'
    assert source_kind('storage.courtlistener.com/recap/gov.uscourts.dcd.223205/x.pdf') == 'court or legal'
    assert source_kind('media.defense.gov/2026/Jun/08/x.pdf') == 'government'
    assert source_kind('metr.org/blog/2026-08-26-incident') == 'research'
    assert source_kind('blog.youtube/inside-youtube/a-personal-update-from-susan') == 'organisation'
