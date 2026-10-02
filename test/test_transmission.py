"""Run from the repo root: python -m pytest test/"""
import numpy as np

from src.features.candidates import mine_candidates
from src.features.copying import CopyIndex, chinese_runs
from src.features.pairs import aggregate, feature_matrix
from src.features.quoting import quoted_anchor
from src.model.model1 import fake_data, fit


def test_em_without_labels_recovers_the_latent_class_model():
    X, y, z, n_levels, truth = fake_data(n=40000, seed=1)
    params, r, history = fit(X, y, n_levels, positive_hint={0: [1], 1: [1], 2: [1], 3: [3]})
    assert (np.diff(history) >= -1e-9).all()
    assert abs(params.pi - 0.02) < 0.005
    for th, true in zip(params.theta, truth):
        assert np.abs(th - true).max() < 0.08
    assert ((r > 0.5) == z).mean() > 0.98


def test_labels_fix_z_and_weights_equal_repeated_rows():
    X, y, z, n_levels, _ = fake_data(n=5000, n_labelled=200, seed=3)
    hint = {0: [1], 1: [1], 2: [1], 3: [3]}
    p_full, r, _ = fit(X, y, n_levels, positive_hint=hint)
    labelled = ~np.isnan(y)
    assert (r[labelled] == y[labelled]).all()
    Xu, yu, w, row_of = aggregate(X, y)
    p_agg, r_agg, _ = fit(Xu, yu, n_levels, w=w, positive_hint=hint)
    assert abs(p_full.pi - p_agg.pi) < 1e-9 and np.allclose(r, r_agg[row_of])


def test_copies_come_from_the_index_and_common_runs_do_not_count():
    zh = {'cac': '第七条 ……使用具有合法来源的数据和基础模型。人工智能', 'p1': '人工智能 新闻', 'p2': '人工智能 技工'}
    en = 'The "Interim Measures" say data must have "legitimate sources" (具有合法来源), and (人工智能) too.'
    assert chinese_runs(en) == {'具有合法来源', '人工智能'}
    assert dict(CopyIndex(zh, max_df=2).copied(en)) == {'cac': {'具有合法来源'}}   # 人工智能 is in 3 documents


def test_candidates_and_their_feature_codes():
    links = {('e1', 'z1')}
    pairs = mine_candidates(links, copies={'e2': {'z1': {'具有合法来源'}}})
    assert pairs == [('e1', 'z1'), ('e2', 'z1')]
    vec = {'e1': np.array([1.0, 0.0]), 'e2': np.array([0.0, 1.0]), 'z1': np.array([0.8, 0.6])}
    X = feature_matrix(pairs, links, {('e1', 'z1'): 1}, {'e2': {'z1': {'具有合法来源'}}}, vec, vec,
                       {'e1': 100, 'e2': None}, {'z1': 98})
    assert X.tolist() == [[1, 1, 0, 4, 1], [0, -1, 1, 4, -1]]   # cosines 0.8, 0.6: top bin (>= 0.6); gap 2 days


def test_a_link_in_quotation_marks():
    p = 'This “umbrella governance” first establishes the legal central authority.'
    assert quoted_anchor(p, 'umbrella governance') == 1
    assert quoted_anchor('China, meanwhile, has released “ interim measures ” for managing AI', 'interim measures') == 1
    assert quoted_anchor('The rules, published by the CAC, apply to services', 'published') == 0
    assert quoted_anchor('text', 'not there') == -1


def test_em_objective_never_decreases_with_labels_missing_values_weights_and_fixed_theta():
    for seed in range(5):
        X, y, _, n_levels, _ = fake_data(n=3000, n_labelled=100, seed=seed)
        rng = np.random.default_rng(seed)
        X[rng.random(X.shape) < 0.1] = -1                        # missing values
        w = rng.integers(1, 5, len(y)).astype(float)              # weighted rows
        _, _, history = fit(X, y, n_levels, w=w, positive_hint={0: [1], 1: [1], 2: [1], 3: [3]},
                            fixed={1: {0: [0.999, 0.001]}})       # copy under z=0 fixed at eps
        assert len(history) > 2 and (np.diff(history) >= -1e-9).all()   # log-likelihood + log-prior
