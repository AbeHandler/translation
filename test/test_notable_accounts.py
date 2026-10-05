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


def test_short_or_common_handles_and_rare_names_alone_are_not_matched():
    accounts = NotableAccounts(ROWS + [
        {'handle': 'BY', 'name': 'Binali Yildirim', 'sitelinks': 80, 'human': True, 'qid': 'Q3'},
        {'handle': 'gmail', 'name': 'Gmail', 'sitelinks': 90, 'human': False, 'qid': 'Q4'},
        {'handle': 'v1t0', 'name': 'Vito Rossi', 'sitelinks': 1, 'human': True, 'qid': 'Q5'}])
    assert accounts.match('written BY @BY and mail me at abc@gmail.com') == []
    assert accounts.match('vito rossi said') == []                     # name only, 1 Wikipedia edition
    assert [m['handle'] for m in accounts.match('@v1t0 posted')] == ['v1t0']   # by handle it still counts


def test_a_name_must_be_written_as_a_name():
    accounts = NotableAccounts(ROWS + [{'handle': 'thegamee', 'name': 'The Game', 'sitelinks': 85, 'human': True,
                                        'qid': 'Q6'}])
    assert accounts.match('The Game is about to start, the game is on') == []
    assert accounts.match('eric trump said') == []
