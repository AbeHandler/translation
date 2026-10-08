"""Run from the repo root: python -m pytest test/"""
from src.fightin.documents import is_english, is_templated

EN = ('The company said on Monday that it would release a new model to the public, and that the model is '
      'safer than the ones it has released before. ') * 4
RO = ('Compania a anunțat luni că va lansa un nou model, care apare prima dată în România și este mai sigur '
      'decât cele lansate înainte de această dată. ') * 4


def test_is_english():
    assert is_english(EN) and not is_english(RO) and not is_english('short text')


def test_is_templated():
    assert is_templated('According to MarketBeat, the stock has a consensus Buy rating.')
    assert not is_templated(EN)
