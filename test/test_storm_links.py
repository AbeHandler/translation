"""Run from the repo root: python -m pytest test/"""
import numpy as np

from src.storm_links import candidate_links, in_window, storm_text


def storm(first, last, title, seeds=()):
    return {'first': first, 'last': last, 'title': title, 'n_articles': 5,
            'seeds': [{'document': s} for s in seeds], 'articles': [{'title': title + ' (copy)'}]}


def test_window():
    en = storm('2024-07-18', '2024-07-20', 'x')
    assert in_window(en, storm('2024-07-19', '2024-07-19', 'y'))
    assert in_window(en, storm('2024-08-02', '2024-08-02', 'y'))
    assert not in_window(en, storm('2024-08-10', '2024-08-10', 'y'))
    assert not in_window(en, storm('2024-07-10', '2024-07-10', 'y'))


def test_links_by_seed_or_similarity():
    en = [storm('2024-07-18', '2024-07-20', 'GPT-4o mini', ['openai.com/index/gpt-4o-mini']),
          storm('2024-07-18', '2024-07-20', 'Chip tariffs')]
    zh = [storm('2024-07-19', '2024-07-22', 'GPT-4o mini发布', ['openai.com/index/gpt-4o-mini']),
          storm('2024-07-19', '2024-07-22', '芯片关税'), storm('2025-01-01', '2025-01-02', '芯片关税')]
    en_vecs, zh_vecs = np.eye(2), np.array([[0.3, 0.1], [0.1, 0.9], [0.1, 0.9]])
    links = candidate_links(en, zh, en_vecs, zh_vecs, min_similarity=0.5)
    assert [(lk['zh'], lk['en'], lk['shared_seeds']) for lk in links] == \
        [(0, 0, ['openai.com/index/gpt-4o-mini']), (1, 1, [])]     # the 2025 storm is out of the window
    assert 'GPT-4o mini (copy)' in storm_text(en[0])
