"""Run from the repo root: python -m pytest test/"""
from src.source_texts import TRUTH_POST, X_POST, html_text, source_path


def test_one_file_per_url_variants_included():
    post = 'https://x.com/sama/status/1790075827666796666'
    assert source_path('/d', post).endswith('.json')
    assert source_path('/d', post) == source_path('/d', 'https://twitter.com/sama/status/1790075827666796666?s=20')
    assert source_path('/d', post) != source_path('/d', 'https://x.com/sama/status/2')


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


def test_the_to_do_list_takes_urls_with_or_without_https(tmp_path):
    from src.source_texts import read_todo
    (tmp_path / 'todo.tsv').write_text('url\nanthropic.com/news/statement-department-of-war\n'
                                       'https://www.anthropic.com/news/statement-department-of-war?utm=x\n'
                                       'https://x.com/sama/status/1\n\nnot a url\n')
    assert sorted(read_todo(str(tmp_path / 'todo.tsv')).values()) == [
        'https://anthropic.com/news/statement-department-of-war', 'https://x.com/sama/status/1']
