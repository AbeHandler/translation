"""Run from the repo root: python -m pytest test/"""
from src.source_matching import SourceIndex, is_listing

POST = ('We have identified industrial-scale campaigns by three AI laboratories, DeepSeek, Moonshot, and MiniMax, '
        'to illicitly extract Claude capabilities to improve their own models through distillation attacks.')


def test_a_screenshot_matches_the_post_it_shows_despite_ocr_noise():
    index = SourceIndex([{'url': 'https://anthropic.com/news/detecting-and-preventing-distillation-attacks',
                          'title': 'Detecting and preventing distillation attacks', 'text': POST},
                         {'url': 'https://anthropic.com/news/claude-4', 'title': 'Claude 4', 'text': 'Introducing '
                          'Claude Opus 4 and Claude Sonnet 4, setting new standards for coding.'}])
    ocr = ('A\\ Anthropic @ @AnthropicAl 显示 翻译 We have identified industrial-scale campaigns by three Al laboratories, '
           'DeepSeek, Moonshot, and MiniMax, to illicitly extract Claude capabilities to improve their own models')
    (url, shared), = index.match(ocr)
    assert url.endswith('distillation-attacks') and shared >= 5
    assert index.match('Tonight we reached an agreement with the Department of War') == []


def test_listing_pages_are_not_sources():
    assert is_listing('https://anthropic.com/news') and is_listing('https://openai.com/')
    assert not is_listing('https://anthropic.com/news/claude-4') and not is_listing('https://openai.com/sam-and-jony')


def test_overlap_is_the_passages_in_common():
    from src.source_matching import overlap_spans, phrases
    source = 'This expansion will help us serve this rapidly growing customer demand. These greater resources'
    ocr = 'Gu 显示 翻译 This expansion will help us serve this rapidly growing customer demand. Read more'
    expected = 'this expansion will help us serve this rapidly growing customer demand'
    assert overlap_spans(ocr, phrases(source)) == [expected]
