"""Run from the repo root: python -m pytest test/"""
import numpy as np

from src.crossings import FEATURES, N_LEVELS, feature_row, seed_summary, sentence_scores


def test_feature_codes():
    translated = {'link': 0, 'screenshot': 1, 'en_quote': 0, 'doc_sim': 0.86, 'sent_sim': 0.92, 'date_gap': 2}
    linked = {'link': 1, 'screenshot': 0, 'en_quote': 0, 'doc_sim': 0.38, 'sent_sim': None, 'date_gap': None}
    assert feature_row(translated) == [0, 1, 0, 4, 4, 1]
    assert feature_row(linked) == [1, 0, 0, 1, -1, -1]
    assert len(FEATURES) == len(N_LEVELS) == len(feature_row(linked))


def test_sentence_scores_count_translation_like_matches():
    seed = np.eye(3)[:2]                       # two seed sentences
    article = np.array([[0.9, np.sqrt(1 - 0.81), 0], [0, 0, 1]])
    best, n = sentence_scores(seed, article)
    assert round(best, 2) == 0.9 and n == 1
    assert sentence_scores([], article) == (None, 0)


def test_seed_summary():
    seed = {'seed_id': 's', 'url': 'u', 'kind': 'organisation', 'organisation': 'anthropic.com',
            'first_seen': '2026-02-26'}
    pairs = [{'p_crossed': 0.97, 'date': '2026-02-28', 'outlet': 'huxiu.com', 'link': 0, 'screenshot': 1,
              'en_quote': 0, 'sent_sim': 0.92},
             {'p_crossed': 0.80, 'date': '2026-03-01', 'outlet': 'thepaper.cn', 'link': 1, 'screenshot': 0,
              'en_quote': 0, 'sent_sim': 0.3},
             {'p_crossed': 0.01, 'date': '2026-02-27', 'outlet': '36kr.com', 'link': 0, 'screenshot': 0,
              'en_quote': 0, 'sent_sim': 0.3}]
    s = seed_summary(seed, pairs)
    assert (s['crossed'], s['zh_outlets'], s['first_zh'], s['lag_days']) == (1, 2, '2026-02-28', 2)
    assert (s['by_link'], s['by_screenshot'], s['translated'], s['candidates']) == (1, 1, 1, 3)
