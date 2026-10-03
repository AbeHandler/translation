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


def test_english_needs_words_or_a_handle_not_just_model_numbers():
    from src.clip import is_english
    assert is_english('Experts debunk fringe theory linking China’s coronavirus to weapons research')
    assert is_english('kopite7kimi @kopite7kimi GeForce RTX 5090 PG144/145-SKU30 GB202-300-A1')
    assert is_english('Eric Trump @ Se) We are so backll!')
    assert not is_english('Vy GEFORCE RTX F- RTX4060Ti 4060Ti')
    assert not is_english('mse Tid dad AAA A Ach hed See eee = pga Chinanews.com', latin_conf=29.9)   # OCR noise
    assert is_english('Experts debunk fringe theory linking China’s coronavirus', latin_conf=83.0)
    assert not is_english('英 伟 达 tesla a100 BF, 40/806 cs 制版 6.3w/ 定制 版 3.7W 站 100 片 40g+100 片 80')


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
