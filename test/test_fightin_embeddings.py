"""Run from the repo root: python -m pytest test/"""
import numpy as np

from src.fightin.embeddings.backends import from_dict, from_encoder, read_vec
from src.fightin.embeddings.index import VectorIndex
from src.fightin.embeddings.lookup import WordLookup

EN = {'governance': [1, 0.1, 0], 'regulation': [0.9, 0.2, 0], 'weapons': [0, 1, 0], 'missiles': [0.1, 0.95, 0],
      'babies': [0, 0, 1]}
ZH = {'治理': [0.95, 0.1, 0.05], '武器': [0.05, 1, 0]}


def index():
    idx = VectorIndex()
    idx.add(*from_dict(EN), lang='en')
    idx.add(*from_dict(ZH), lang='zh')
    return idx


def test_nearest_words_overall_and_per_language():
    idx = index()
    (w, lang, s), = idx.nearest(np.array([1, 0, 0]), k=1)
    assert (w, lang) == ('governance', 'en') and s > 0.99
    assert [w for w, _, _ in idx.nearest(np.array([1, 0, 0]), k=1, lang='zh')] == ['治理']
    assert [w for w, _, _ in idx.nearest(idx.vector('governance', 'en'), k=1, exclude=[('en', 'governance')])][0] in \
        ('治理', 'regulation')


def test_lookup_similarity_and_describe():
    look = WordLookup(index())
    assert look.similarity('governance', '治理', 'en', 'zh') > 0.9 > look.similarity('governance', '武器', 'en', 'zh')
    near = [w for w, _, _ in look.describe(['weapons'], lang='en', k=2)]
    assert near[0] in ('missiles', '武器') and 'weapons' not in near
    assert look.describe(['not-a-word'], lang='en') == []


def test_save_and_load(tmp_path):
    idx = index()
    idx.save(tmp_path / 'i.npz')
    back = VectorIndex.load(tmp_path / 'i.npz')
    assert len(back) == len(idx) and np.allclose(back.vector('治理', 'zh'), idx.vector('治理', 'zh'))


def test_read_vec_and_from_encoder(tmp_path):
    (tmp_path / 'tiny.vec').write_text('3 2\nthe 0.1 0.2\ngovernance 1 0\n治理 0.9 0.1\n', encoding='utf-8')
    words, vecs = read_vec(tmp_path / 'tiny.vec', max_words=2)
    assert words == ['the', 'governance'] and vecs.shape == (2, 2)
    words, vecs = read_vec(tmp_path / 'tiny.vec', keep=lambda w: w != 'the')
    assert words == ['governance', '治理']
    words, vecs = from_encoder(['a', 'b', 'a'], lambda ws: [[len(w), 1] for w in ws])
    assert words == ['a', 'b'] and vecs.shape == (2, 2)
