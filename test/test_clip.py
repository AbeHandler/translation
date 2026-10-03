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
    assert not is_english('英 伟 达 tesla a100 BF, 40/806 cs 制版 6.3w/ 定制 版 3.7W 站 100 片 40g+100 片 80')
