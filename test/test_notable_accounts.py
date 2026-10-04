"""Run from the repo root: python -m pytest test/"""
from src.notable_accounts import NotableAccounts, parse_wikidata_tsv

ROWS = [
    {'handle': 'reidhoffman', 'name': 'Reid Hoffman', 'sitelinks': 31, 'human': True, 'qid': 'Q211098'},
    {'handle': 'Google', 'name': 'Google', 'sitelinks': 211, 'human': False, 'qid': 'Q95'},
    {'handle': 'erictrump', 'name': 'Eric Trump', 'sitelinks': 45, 'human': True, 'qid': 'Q1'},
    {'handle': 'nobody', 'name': 'No Body', 'sitelinks': 0, 'human': True, 'qid': 'Q2'},   # no Wikipedia article
]


def test_wikidata_tsv_is_parsed():
    text = ('?item\t?handle\t?name\t?sitelinks\t?human\n'
            '<http://www.wikidata.org/entity/Q211098>\t"reidhoffman"\t"Reid Hoffman"@en\t31\ttrue\n')
    assert list(parse_wikidata_tsv(text)) == [ROWS[0]]


def test_garbled_handles_and_names_are_matched():
    accounts = NotableAccounts(ROWS)
    found = accounts.match('A few words on AI & Reid Hoffman @ @reidhoffman . 3 月 4 日 | G Google & @Google .10 小时')
    assert [(m['handle'], m['how']) for m in found] == [('reidhoffman', 'handle'), ('Google', 'handle')]
    assert [(m['name'], m['how']) for m in accounts.match('Eric Trump @ Se) We are so backll!')] == \
        [('Eric Trump', 'name')]


def test_accounts_without_a_wikipedia_article_and_single_word_names_are_not_matched():
    accounts = NotableAccounts(ROWS)
    assert accounts.match('@nobody No Body said Google is great') == []
