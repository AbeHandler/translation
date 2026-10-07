"""Run from the repo root: python -m pytest test/"""
import numpy as np

from src.drift.quotes import is_quoted, quoted_spans
from src.drift.scorers import EmbeddingDrift, NLIDrift
from src.drift.types import BROADER, CONTRADICTED, EQUIVALENT, NARROWER, SHIFTED


def nli_table(table):
    """A fake NLI: entailment probability per (premise, hypothesis), the rest neutral."""
    def nli(premise, hypothesis):
        e, c = table.get((premise, hypothesis), (0.1, 0.0))
        return {'entailment': e, 'neutral': 1 - e - c, 'contradiction': c}
    return nli


def test_nli_kinds():
    cases = {EQUIVALENT: {('s', 'r'): (0.9, 0), ('r', 's'): (0.8, 0)},
             BROADER: {('s', 'r'): (0.9, 0)},
             NARROWER: {('r', 's'): (0.9, 0)},
             SHIFTED: {},
             CONTRADICTED: {('s', 'r'): (0.1, 0.8)}}
    for kind, table in cases.items():
        assert NLIDrift(nli_table(table)).score('s', 'r').kind == kind
    assert NLIDrift(nli_table(cases[EQUIVALENT])).score('s', 'r').size == 0.15


def test_embedding_drift_is_one_minus_similarity():
    vecs = {'a': np.array([1.0, 0.0]), 'b': np.array([0.6, 0.8])}
    d = EmbeddingDrift(lambda texts: np.array([vecs[t] for t in texts])).score('a', 'b')
    assert (d.size, d.kind, d.details['similarity']) == (0.4, None, 0.6)


def test_quotations():
    text = '他说：「AI将成为一种永远无法满足的商品」。另外“投资不足”。'
    assert [text[a:b] for a, b in quoted_spans(text)] == ['AI将成为一种永远无法满足的商品', '投资不足']
    assert is_quoted((text.index('永远'), text.index('永远') + 2), text)
    assert not is_quoted((0, 2), text)


def test_llm_drift_from_a_json_reply():
    import json
    from src.drift.llm import LLMDrift
    from src.drift.types import DriftScorer
    sent = []

    def chat(messages):
        sent.append(messages[0]['content'])
        return json.dumps({'faithfulness': 2, 'kind': 'shifted', 'changes': 'appetite becomes unmet demand',
                           'direction': 'towards scarcity'})
    scorer = LLMDrift(chat=chat, model='fake')
    d = scorer.score("a commodity we just can't get enough of", '一种永远无法满足的商品')
    assert (d.size, d.kind, d.method, d.details['faithfulness']) == (0.75, 'shifted', 'llm:fake', 2)
    assert "can't get enough of" in sent[0] and '一种永远无法满足的商品' in sent[0]
    odd = LLMDrift(chat=lambda m: json.dumps({'faithfulness': 9, 'kind': 'weird'}), model='fake').score('a', 'b')
    assert (odd.size, odd.kind) == (0.0, None)                                   # clamped; unknown kinds dropped
    assert isinstance(scorer, DriftScorer)


def test_every_scorer_meets_the_interface():
    from src.drift.llm import LLMDrift
    from src.drift.types import DriftScorer
    for scorer in (EmbeddingDrift(lambda t: None), NLIDrift(nli_table({})), LLMDrift(chat=lambda m: '{}', model='x')):
        assert isinstance(scorer, DriftScorer) and scorer.name
