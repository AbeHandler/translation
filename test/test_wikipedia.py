"""Run from the repo root: python -m pytest test/"""
from src.wikipedia.dump import chunks, parse_page
from src.ai_mentions import mentions_ai
from src.wikipedia.links import external_links


def test_ai_as_a_word_of_its_own_also_next_to_chinese():
    assert mentions_ai('AI safety; generative AI. AI芯片 和 人工智能（AI）') == 4
    assert mentions_ai('MAIL, Aida, Ai Weiwei, AIDS, OpenAI') == 0


def test_external_links_from_cites_and_brackets_without_archives_or_wikis():
    text = ('Claim.<ref>{{cite web |url=https://www.xinhuanet.com/a.htm |archive-url=https://web.archive.org/'
            'web/2020/https://www.xinhuanet.com/a.htm |title=T}}</ref> See [https://openai.com/index/x OpenAI]. '
            'Also https://en.wikipedia.org/wiki/AI and (https://example.com/p).')
    assert external_links(text) == ['https://www.xinhuanet.com/a.htm', 'https://openai.com/index/x',
                                    'https://example.com/p']


def test_chunks_and_pages():
    assert chunks([10, 20, 30, 40, 50], 60, 2) == [(10, 30), (30, 50), (50, 60)]
    page = parse_page('<page><title>人工智能</title><ns>0</ns><id>7</id><revision><text>AI</text></revision></page>')
    assert (page.page_id, page.title, page.ns, page.redirect, page.text) == (7, '人工智能', 0, False, 'AI')
