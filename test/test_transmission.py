"""Run from the repo root: python -m pytest test/"""
import numpy as np

from src.transmission.model1 import Params, fake_data, fit, loglik
from src.transmission.pairs import build_pairs, chinese_runs, copies, nearest


def test_em_never_decreases_the_likelihood_and_recovers_the_parameters():
    L, c, y, _ = fake_data(n=20000, n_labelled=2000, seed=1)
    params, r, history = fit(L, c, y)
    assert (np.diff(history) >= -1e-9).all()
    assert abs(params.pi1 - 0.6) < 0.05 and abs(params.pi0 - 0.05) < 0.02 and abs(params.gamma1 - 0.25) < 0.05
    assert history[-1] == loglik(params, L, c, y)


def test_labels_fix_z_and_a_copy_makes_transmission_near_certain():
    L, c, y = np.array([1., 1., 0., 0.]), np.array([0., 1., 1., 0.]), np.array([0., np.nan, np.nan, np.nan])
    _, r, _ = fit(L, c, y, init=Params())
    assert r[0] == 0 and r[1] > 0.99 and r[2] > 0.9 and r[3] < 0.5


def test_copies_need_a_shared_run_of_four_chinese_characters():
    en = 'The "Interim Measures for Generative AI" (生成式人工智能服务管理暂行办法) say data must have "legitimate sources" (具有合法来源).'
    assert chinese_runs(en) == {'生成式人工智能服务管理暂行办法', '具有合法来源'}
    assert copies(en, '第七条 ……使用具有合法来源的数据和基础模型') == 1
    assert copies('China (中国) passed rules', '中国网信办') == 0      # 2 characters: too short to count


def test_pairs_are_links_plus_neighbours_with_known_texts():
    rows = build_pairs(links=[('e1', 'z1')], neighbours={'e1': ['z1', 'z2'], 'e2': ['z3']},
                       en_texts={'e1': 'x 具有合法来源', 'e2': 'y'}, zh_texts={'z1': '具有合法来源的', 'z2': 'b'},
                       labels={('e1', 'z1'): 1})
    assert rows == [{'doc_en': 'e1', 'doc_zh': 'z1', 'L': 1, 'c': 1, 'y': 1},
                    {'doc_en': 'e1', 'doc_zh': 'z2', 'L': 0, 'c': 0, 'y': ''}]
    assert nearest(np.eye(2), np.array([[0., 1.], [1., 0.]]), 1) == [[1], [0]]
