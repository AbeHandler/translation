"""Run from the repo root: python -m pytest test/"""
from src.source_texts import TRUTH_POST, X_POST, html_text, source_path


def test_one_file_per_document():
    assert source_path('/d', 'x.com/sama/status/1').endswith('.json')
    assert source_path('/d', 'x.com/sama/status/1') == source_path('/d', 'x.com/sama/status/1')
    assert source_path('/d', 'x.com/sama/status/1') != source_path('/d', 'x.com/sama/status/2')


def test_posts_are_recognised():
    assert X_POST.match('https://twitter.com/sama/status/1679602638562918405').group(1) == '1679602638562918405'
    assert X_POST.match('https://x.com/sama/status/1790075827666796666?s=20')
    assert TRUTH_POST.match('https://truthsocial.com/@realDonaldTrump/posts/115684148454828379').group(1)
    assert not X_POST.match('https://x.com/sama')


def test_html_text_keeps_the_article():
    html = ('<html><head><title>A personal update from Susan</title></head><body><nav>Home | News</nav>'
            '<article><p>' + 'Twenty-five years ago I made a decision to rent out my garage. ' * 10 +
            '</p></article></body></html>')
    title, text = html_text(html)
    assert 'Susan' in title and 'garage' in text and 'Home | News' not in text
