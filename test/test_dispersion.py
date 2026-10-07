import numpy as np

from src.dispersion.align import align
from src.dispersion.aligners.dictionary import DictionaryAligner
from src.dispersion.dispersion import dispersion
from src.dispersion.evaluate import overlap_f1, score
from src.dispersion.locate import occurrences, sentences
from src.dispersion.sentences import SentenceMatcher
from src.dispersion.types import DROPPED, NOT_FOUND, RENDERED, Doc, Focal

SOURCE = Doc('src', 'en', 'We need better AI governance. Prices fell. Governance matters for frontier models.')
TARGET = Doc('tgt', 'zh', '我们需要更好的人工智能治理。价格下降了。对于前沿模型，管控很重要。')


class TopicEncoder:
    """A fake encoder: each sentence becomes a one-hot of the topic words it holds."""
    TOPICS = [('governance', '治理'), ('price', '价格'), ('frontier', '前沿')]

    def __call__(self, texts):
        vecs = np.array([[float(en in t.lower() or zh in t) for en, zh in self.TOPICS] for t in texts]) + 1e-6
        return vecs / np.linalg.norm(vecs, axis=1, keepdims=True)


def test_sentences_keep_their_offsets():
    for s in sentences(TARGET.text, 'zh') + sentences(SOURCE.text, 'en'):
        text = TARGET.text if '。' in s.text else SOURCE.text
        assert text[s.span[0]:s.span[1]] == s.text


def test_occurrences_by_text_or_span():
    assert occurrences(Focal('governance', 'en'), SOURCE.text) == [(18, 28), (43, 53)]
    assert occurrences(Focal('governance', 'en', span=(18, 28)), SOURCE.text) == [(18, 28)]


def test_align_one_prediction_per_occurrence():
    aligner = DictionaryAligner({'governance': ['治理', '管控']})
    preds = align(Focal('governance', 'en'), SOURCE, TARGET, SentenceMatcher(TopicEncoder(), min_score=0.5), aligner)
    assert [p.status for p in preds] == [RENDERED, RENDERED]
    assert [p.target_text for p in preds] == ['治理', '管控']
    assert all(TARGET.text[a:b] == p.target_text for p in preds for a, b in p.target_spans)


def test_dropped_and_not_found():
    aligner = DictionaryAligner({'prices': ['不存在']})
    matcher = SentenceMatcher(TopicEncoder(), min_score=0.7)   # the fake's no-topic vector scores ~0.58
    (fell,) = align(Focal('Prices', 'en'), SOURCE, TARGET, matcher, aligner)
    assert fell.status == DROPPED and fell.target_sentence.text == '价格下降了。'
    (gone,) = align(Focal('Prices', 'en'), SOURCE, Doc('t', 'zh', '无关的句子。'), matcher, aligner)
    assert gone.status == NOT_FOUND


def test_dispersion_counts_renderings():
    aligner = DictionaryAligner({'governance': ['治理', '管控']})
    preds = align(Focal('governance', 'en'), SOURCE, TARGET, SentenceMatcher(TopicEncoder(), min_score=0.5), aligner)
    d = dispersion(preds + preds)
    assert d['distinct'] == 2 and d['entropy'] == 1.0 and d['rendered'] == 4


def test_split_spans_and_scoring():
    assert overlap_f1([(0, 4), (6, 8)], [(0, 4), (6, 8)]) == 1.0
    assert overlap_f1([(0, 4)], [(0, 4), (6, 8)]) == round(2 * 4 / (4 + 6), 10)
    assert overlap_f1([], []) == 1.0 and overlap_f1([], [(0, 2)]) == 0.0
    assert score([([(0, 2)], [(0, 2)]), ([], [(0, 2)])]) == {'n': 2, 'exact': 0.5, 'f1': 0.5}


def test_tokens_keep_offsets_and_adjacent_spans_merge():
    from src.dispersion.tokens import merge_spans, tokens
    text = 'We need GPT-4o governance.'
    assert [text[a:b] for w, a, b in tokens(text, 'en')][2:4] == ['GPT-4o', 'governance']
    zh = '前沿人工智能模型可以用于完全自主的武器'
    assert all(zh[a:b] == w for w, a, b in tokens(zh, 'zh'))
    assert merge_spans([(0, 2), (2, 4), (6, 8)], 'ABCDEFGH') == [(0, 4), (6, 8)]
    assert merge_spans([(0, 2), (3, 5)], 'AB CD') == [(0, 5)]


class FakeSimAlign:
    """Stands in for simalign.SentenceAligner: aligns token i to the token holding the same index in a table."""
    def __init__(self, pairs):
        self.pairs = pairs

    def get_word_aligns(self, src, tgt):
        return {'itermax': self.pairs}


def test_simalign_aligner_maps_focal_words_to_target_pieces():
    from src.dispersion.aligners.simalign import SimAlignAligner
    from src.dispersion.tokens import tokens
    src, tgt = 'fully autonomous weapons', '完全自主的武器'
    zh_words = [w for w, _, _ in tokens(tgt, 'zh')]
    pairs = [(0, zh_words.index('完全')), (1, zh_words.index('自主')), (2, zh_words.index('武器'))]
    aligner = SimAlignAligner('en', 'zh', aligner=FakeSimAlign(pairs))
    spans, score = aligner.align((6, 24), src, tgt)              # "autonomous weapons"
    assert '…'.join(tgt[a:b] for a, b in spans) == '自主…武器' and score == 1.0
