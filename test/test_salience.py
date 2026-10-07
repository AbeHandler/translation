"""Run from the repo root: python -m pytest test/"""
from src.salience import quoted_passages, seed_salience
from src.source_matching import phrases

SEED = ("First, we do not believe that today's frontier AI models are reliable enough to be used in fully autonomous "
        "weapons. Second, mass domestic surveillance of Americans constitutes a violation of fundamental rights.")


def test_quoted_passages_are_the_verbatim_runs():
    article = ('The company said: "First, we do not believe that today\'s frontier AI models are reliable enough to be '
               'used in fully autonomous weapons," and left it there.')
    assert quoted_passages(article, phrases(SEED)) == [
        'first we do not believe that today s frontier ai models are reliable enough to be used in fully autonomous '
        'weapons']
    assert quoted_passages('Anthropic said no to the Pentagon.', phrases(SEED)) == []


def test_salience_per_language():
    seed = {'seed_id': 's', 'url': 'u', 'kind': 'organisation', 'organisation': 'anthropic.com',
            'first_seen': '2026-02-26', 'text_status': 'text'}
    cites = [{'language': 'en', 'article': 'a', 'outlet': 'x.com', 'date': '2026-02-27', 'n_chars': 900,
              'n_passages': 1},
             {'language': 'en', 'article': 'b', 'outlet': 'y.com', 'date': '2026-04-01', 'n_chars': 900,
              'n_passages': 0},
             {'language': 'zh', 'article': 'c', 'outlet': 'huxiu.com', 'date': '2026-03-02', 'n_chars': 0,
              'n_passages': 0}]
    row = seed_salience(seed, cites)
    assert (row['en_articles'], row['en_outlets'], row['en_outlets_14d'], row['en_lag_days']) == (2, 2, 1, 1)
    assert (row['en_quoting'], row['en_quoting_share']) == (1, 0.5)
    assert (row['zh_articles'], row['zh_lag_days'], row['zh_with_text'], row['zh_quoting_share']) == (1, 4, 0, '')
