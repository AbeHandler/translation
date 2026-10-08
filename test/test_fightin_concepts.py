"""Run from the repo root: python -m pytest test/"""
from src.fightin.concepts import concept_counts, nearest_pivots, normalise, pivot_concepts, read_stopwords
from src.fightin.embeddings.backends import from_dict
from src.fightin.embeddings.index import VectorIndex


def index():
    idx = VectorIndex()
    idx.add(*from_dict({'governance': [1, 0, 0], 'chips': [0, 1, 0]}), lang='en')
    idx.add(*from_dict({'治理': [0.95, 0.1, 0], '芯片': [0, 0.9, 0.1], '了': [0, 0, 1]}), lang='zh')
    return idx


def test_normalise():
    assert [normalise(w) for w in ['OpenAI', 'GPT-4o', '治理', '2025', '，', 'AI']] == \
        ['openai', 'gpt-4o', '治理', '', '', 'ai']


def test_chinese_words_map_to_close_english_words_only():
    m = pivot_concepts(index(), ['治理', '芯片', '了', 'ai', '未知'], threshold=0.8)
    assert m['治理'][0] == 'governance' and m['芯片'][0] == 'chips'
    assert m['了'][0] == '了' and m['ai'] == ('ai', 1.0) and m['未知'] == ('未知', 0.0)


def test_concept_counts():
    m = pivot_concepts(index(), ['治理', '芯片'], threshold=0.8)
    assert concept_counts([['治理', '芯片', '治理', 'ai']], m) == {'governance': 2, 'chips': 1, 'ai': 1}
    assert concept_counts([['governance', 'the']]) == {'governance': 1, 'the': 1}
    # stopword concepts dropped, also when a Chinese word maps to one (该 -> the)
    m = {'治理': ('governance', 0.9), '该': ('the', 0.8)}
    assert concept_counts([['治理', '该']], m, frozenset({'the'})) == {'governance': 1}


def test_read_stopwords(tmp_path):
    (tmp_path / 's.txt').write_text('# comment\nthe\n\nof\n', encoding='utf-8')
    assert read_stopwords(tmp_path / 's.txt') == {'the', 'of'}


def test_nearest_pivots_even_below_the_threshold():
    near = nearest_pivots(index(), ['治理', '了', 'ai'])
    assert near['治理'][0] == 'governance' and near['了'][1] < 0.5 and 'ai' not in near
    m = pivot_concepts(index(), ['了'], threshold=0.8, nearest=near)
    assert m['了'][0] == '了'          # below the threshold: its own concept; the gloss comes from nearest
