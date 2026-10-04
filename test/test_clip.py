"""Run from the repo root: python -m pytest test/"""
import numpy as np

from src.clip import ImageClassifier, body_images


class FakeModel:   # 'images' and class descriptions are strings here; each lands on one axis
    def encode(self, items, **kwargs):
        axes = ['tweet', 'photo', 'chart']
        return np.array([[float(a in str(item)) for a in axes] for item in items])


def test_an_image_gets_the_class_whose_description_it_is_closest_to():
    clf = ImageClassifier(model=FakeModel(), classes={'tweet': 'a tweet', 'photo': 'a photo', 'chart': 'a chart'})
    (label, score, scores), (label2, _, _) = clf.classify(['looks like a tweet', 'a photo of people'])
    assert label == 'tweet' and score > 0.99 and label2 == 'photo'


def test_body_images_are_absolute_and_lazy_sources_win():
    para = '<p>' + '美国将出台新规，进一步限制GPU出口中国。' * 20 + '</p>'
    html = (f'<html><body><nav><img src="/logo.png"></nav><article>{para}'
            f'<img src="/blank.gif" data-src="/a/shot.jpg" alt="截图来自《华盛顿邮报》">{para}</article></body></html>')
    assert body_images(html, 'https://news.sina.com.cn/c/1.shtml') == [
        {'src': 'https://news.sina.com.cn/a/shot.jpg', 'alt': '截图来自《华盛顿邮报》'}]


def test_latin_share_tells_english_screenshots_from_chinese_ones():
    from src.clip import latin_share
    assert latin_share('Experts debunk fringe theory linking China’s coronavirus') == 1.0
    assert latin_share('美国将出台新规，进一步限制GPU出口中国') < 0.3


def test_english_screenshots_are_tweets_with_a_handle_or_prose_not_interfaces():
    from src.clip import english_kind
    assert english_kind('kopite7kimi @kopite7kimi GeForce RTX 5090 PG144/145-SKU30', 'post') == 'tweet'
    assert english_kind('Eric Trump @ Se) We are so backll!', 'post') == 'tweet'
    assert english_kind("Although Cotton's views break with medical experts, they're in keeping with his longtime "
                        'opposition to the Chinese government', 'page') == 'prose'
    assert english_kind('About Contact/Submission = The AI bubble and the U.S. economy By Michael Roberts (Posted Oct '
                        '17, 2025) | Originally published: The Next Recession', 'page') == 'prose'
    for ui in ['Home > Video Games » PlayStation > PlayStation 5 > PS5 Accessories > PS5 Controllers » Details',
               'netflix_datapipeline > broker_offline_process_alert Jul 18th 2016, 12:53 AM Parameters Region',
               'Biological Technologies Office Defense Sciences Office Information Processing Techniques Office',
               'Results SD card 115,168MB total - 105,285MB free Tap to benchmark SD card 115,168MB total']:
        assert english_kind(ui, 'page') is None
    assert english_kind('mse Tid dad AAA A Ach hed See eee = pga Chinanews.com', 'page', latin_conf=29.9) is None
    assert english_kind('Vy GEFORCE RTX F- RTX4060Ti 4060Ti', 'photo') is None


def test_a_crawl_file_is_screened_page_by_page_ai_pages_only(tmp_path, monkeypatch):
    import json
    import pyarrow as pa
    import pyarrow.parquet as pq
    import src.clip as clip
    from src.cc_news import ArticleHtmlArchiver
    monkeypatch.setattr(clip, 'fetch_image', lambda src, page, client: None)   # no network in tests
    para = '<p>' + '人工智能大模型正在改变新闻业。' * 20 + '</p><img src="/shot.jpg" alt="截图来自推特">'
    rows = [{'url': f'https://zh.com/{i}', 'language': 'zh', 'warc_date': '', 'content_type': 'text/html',
             'record_id': str(i), 'html': f'<html><body><article>{text}</article></body></html>'.encode()}
            for i, text in enumerate([para, '<p>' + '今天天气很好。' * 20 + '</p>'])]
    pq.write_table(pa.Table.from_pylist(rows, ArticleHtmlArchiver.SCHEMA), tmp_path / 'part.parquet')
    counts = clip.screen_html_file(str(tmp_path / 'part.parquet'), str(tmp_path / 'out.jsonl'),
                                   classifier=None, ocr=None, client=None)
    assert counts == {'pages': 2, 'screened': 1, 'english_screenshots': 0}
    (row,) = [json.loads(line) for line in open(tmp_path / 'out.jsonl')]
    assert row['url'] == 'https://zh.com/0' and row['images'][0]['src'] == 'https://zh.com/shot.jpg'
