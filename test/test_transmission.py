"""Run from the repo root: python -m pytest test/"""
import numpy as np

from src.transmission.model1 import Params, fake_data, fit, loglik
from src.data.transmission_pairs import CopyIndex, build_pairs, chinese_runs, universe_size


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


def test_copies_come_from_the_index_and_common_runs_do_not_count():
    zh = {'cac': '第七条 ……使用具有合法来源的数据和基础模型。人工智能', 'p1': '人工智能 新闻', 'p2': '人工智能 技工'}
    en = 'The "Interim Measures" say data must have "legitimate sources" (具有合法来源), and (人工智能) too.'
    assert chinese_runs(en) == {'具有合法来源', '人工智能'}
    assert dict(CopyIndex(zh, max_df=2).copied(en)) == {'cac': {'具有合法来源'}}   # 人工智能 is in 3 documents
    found = dict(CopyIndex(zh, max_df=5).copied(en))
    assert found == {'cac': {'具有合法来源', '人工智能'}, 'p1': {'人工智能'}, 'p2': {'人工智能'}}


def test_pairs_are_sparse_plus_a_background_count_and_weights_count_in_the_fit():
    index = CopyIndex({'z1': '具有合法来源的', 'z2': '别的东西别的'}, max_df=5)
    rows = build_pairs(links=[('e1', 'z2')], en_texts={'e1': 'x', 'e2': 'cites 具有合法来源'}, copy_index=index,
                       labels={('e1', 'z2'): 1}, n_universe=100)
    assert [(r['doc_en'], r['doc_zh'], r['L'], r['c'], r['y'], r['w']) for r in rows] == [
        ('e1', 'z2', 1, 0, 1, 1), ('e2', 'z1', 0, 1, '', 1), ('*', '*', 0, 0, '', 98)]
    assert universe_size([10, 20], [5, 10, 30], window_days=10) == 3    # 10-5, 10-10, 20-10
    L, c, y, _ = fake_data(n=4000, seed=2)
    background = (L == 0) & (c == 0) & np.isnan(y)
    keep = ~background
    w = np.ones(keep.sum() + 1)
    w[-1] = background.sum()
    p_full, _, _ = fit(L, c, y, init=Params())
    p_sparse, _, _ = fit(np.append(L[keep], 0), np.append(c[keep], 0), np.append(y[keep], np.nan), init=Params(), w=w)
    assert abs(p_full.pi0 - p_sparse.pi0) < 1e-9 and abs(p_full.gamma1 - p_sparse.gamma1) < 1e-9
