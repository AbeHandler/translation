"""Run from the repo root: python -m pytest test/"""
from src.seeds import merge_seeds, organisation


def source(document, outlets, first, seen, example):
    return {'document': document, 'href': 'https://' + document, 'outlets': outlets, 'outlets_first': first,
            'first_seen': seen, 'example': example}


def test_seeds_merge_both_languages_and_hand_picked_ones():
    en = [source('anthropic.com/news/statement-department-of-war', 300, 250, '2026-02-26', 'https://a.com/1'),
          source('x.com/someone/status/1', 3, 3, '2026-01-01', 'https://b.com/1')]          # too few outlets
    zh = [source('anthropic.com/news/statement-department-of-war', 12, 9, '2026-02-27', 'https://thepaper.cn/1'),
          source('cac.gov.cn/2023-04/11/c_1682854275475410.htm', 40, 30, '2023-04-11', 'https://huxiu.com/1')]
    seeds = merge_seeds(en, zh, ['openai.com/index/an-alien-mind', 'https://x.com/someone/status/1', '# not a url'],
                        min_outlets=5)
    by_key = {s['key']: s for s in seeds}
    war = by_key['anthropic.com/news/statement-department-of-war']
    assert (war['en_outlets'], war['zh_outlets'], war['outlets_first']) == (300, 12, 259)
    assert war['first_seen'] == '2026-02-26'
    assert war['added_from'] == 'links_en+links_zh' and war['organisation'] == 'anthropic.com'
    assert by_key['cac.gov.cn/2023-04/11/c_1682854275475410.htm']['kind'] == 'government'
    assert by_key['openai.com/index/an-alien-mind']['added_from'] == 'manual'
    assert by_key['x.com/someone/status/1']['en_outlets'] == 3      # hand-picked: kept, with its links
    assert seeds[0]['key'] == 'anthropic.com/news/statement-department-of-war'


def test_organisation_is_the_handle_or_the_site():
    assert organisation('x.com/sama/status/1790075827666796666') == '@sama'
    assert organisation('truthsocial.com/@realDonaldTrump/posts/115684148454828379') == '@realDonaldTrump'
    assert organisation('www.anthropic.com/news/claude-4') == 'anthropic.com'
