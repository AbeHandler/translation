import numpy as np

from src.dispersion.aligners.dictionary import DictionaryAligner
from src.dispersion.crossing import PhraseCrossingDetector
from src.dispersion.dispersion import dispersion, selection
from src.dispersion.evaluate import overlap_f1, score
from src.dispersion.locate import occurrences, sentences
from src.dispersion.sentences import SentenceMatcher
from src.dispersion.types import DROPPED, PARAPHRASED, TRANSLATED, VERBATIM, Doc, Focal

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


class WordEncoder:
    """A fake encoder for phrase similarity: texts sharing a meaning (a set) are 1, else 0."""
    MEANINGS = [{'governance', '治理', '管控'}, {'prices', '价格'}]

    def __call__(self, texts):
        vecs = np.array([[float(t.lower() in m) for m in self.MEANINGS] + [1e-3] for t in texts])
        return vecs / np.linalg.norm(vecs, axis=1, keepdims=True)


def detector(renderings, min_score=0.5, known=None):
    return PhraseCrossingDetector(SentenceMatcher(TopicEncoder(), min_score=min_score), DictionaryAligner(renderings),
                                  WordEncoder(), known=known)


def test_one_prediction_per_occurrence_translated():
    preds = detector({'governance': ['治理', '管控']}).detect(Focal('governance', 'en'), SOURCE, TARGET)
    assert [p.uptake for p in preds] == [TRANSLATED, TRANSLATED]
    assert [p.target_text for p in preds] == ['治理', '管控']
    assert all(TARGET.text[a:b] == p.target_text for p in preds for a, b in p.target_spans)


def test_dropped_three_ways_and_verbatim():
    d = detector({'prices': ['下降']}, min_score=0.7)       # the fake's no-topic vector scores ~0.58
    (fell,) = d.detect(Focal('Prices', 'en'), SOURCE, TARGET)
    assert (fell.uptake, fell.reason, fell.target_text) == (DROPPED, 'dissimilar', '下降')   # aligned, unlike it
    (none,) = detector({}, min_score=0.7).detect(Focal('Prices', 'en'), SOURCE, TARGET)
    assert (none.uptake, none.reason) == (DROPPED, 'no span')
    (gone,) = d.detect(Focal('Prices', 'en'), SOURCE, Doc('t', 'zh', '无关的句子。'))
    assert (gone.uptake, gone.reason) == (DROPPED, 'no sentence')
    kept = Doc('k', 'zh', '我们需要更好的AI governance。')
    assert [p.uptake for p in detector({}).detect(Focal('governance', 'en'), SOURCE, kept)][0] == VERBATIM


def test_known_renderings_and_whole_sentences():
    d = detector({'governance': ['人工智能']}, known={'governance': ['人工智能']})
    assert d.detect(Focal('governance', 'en'), SOURCE, TARGET)[0].reason == 'known rendering'
    whole = Focal('Prices fell.', 'en', span=(30, 42))
    (p,) = detector({}).detect(whole, SOURCE, TARGET)
    assert p.level == 'sentence' and p.target_text == '价格下降了。' and p.uptake == TRANSLATED


def test_dispersion_and_selection():
    preds = detector({'governance': ['治理', '管控']}).detect(Focal('governance', 'en'), SOURCE, TARGET)
    d = dispersion(preds + preds)
    assert d['distinct'] == 2 and d['entropy'] == 1.0 and d['rendered'] == 4
    shares = selection(preds + [preds[0].__class__((0, 1), DROPPED, 'no span')])
    assert shares[TRANSLATED] == 0.667 and shares[DROPPED] == 0.333 and shares[PARAPHRASED] == 0.0


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


def test_chinese_ai_terms_stay_whole():
    from src.dispersion.tokens import tokens
    words = [w for w, _, _ in tokens('推动下一代个人智能体发展，大模型与算力', 'zh')]
    assert '智能体' in words and '大模型' in words and '算力' in words


def test_split_renderings_count_as_their_words():
    from src.dispersion.dispersion import normalise
    assert normalise('自主…武器') == normalise('自主武器') == '自主武器'
    assert normalise('training data…processing') == 'training data processing'
    assert normalise('尖端 AI 模型') == '尖端ai模型'
