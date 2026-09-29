"""Run from the repo root: python -m pytest test/"""
from src.link_language.fetch import Page, decode, visible_text
from src.link_language.labeler import HOST_SAMPLE, LinkLanguageLabeler
from src.link_language.script import label_text

ZH = '人工智能公司深度求索发布了新的大模型，引起了广泛关注和讨论。' * 5
EN = 'The artificial intelligence company released a new large language model this week. ' * 5


def test_labels_by_writing_system():
    assert label_text(ZH)[0] == 'zh' and label_text(ZH)[2] == 'script'
    assert label_text(EN)[0] == 'en' and label_text(EN)[1] == 0.0
    assert label_text('日本の人工知能企業が新しいモデルを発表しました。' * 5)[0] == 'ja'
    assert label_text('인공지능 회사가 새로운 모델을 발표했습니다.' * 5)[0] == 'ko'
    assert label_text('too short')[0] == 'unknown'


def test_gbk_pages_decode_and_scripts_are_dropped():
    html = f'<html><head><title>标题</title><script>var x=1;</script></head><body><p>{ZH}</p></body></html>'
    assert decode(html.encode('gbk'), None).startswith('<html>')
    title, text = visible_text(html)
    assert title == '标题' and 'var x' not in text and text.startswith('人工智能')


def test_host_cache_skips_fetching_once_a_host_is_known(tmp_path):
    fetched = []

    def fake_fetch(url, client):
        fetched.append(url)
        return Page(200, url, 'text/html', 'T', ZH)
    labeler = LinkLanguageLabeler(str(tmp_path), fetch=fake_fetch)
    results = [labeler.label({'url': f'https://www.xinhuanet.com/{i}'}) for i in range(HOST_SAMPLE + 2)]
    assert len(fetched) == HOST_SAMPLE
    assert [r['label_source'] for r in results] == ['fetched'] * HOST_SAMPLE + ['host_cache'] * 2
    assert all(r['language'] == 'zh' for r in results)
