"""Drift scorers: each has .name and .score(source, rendering) -> Drift, for a source passage and its rendering in
another language (or the same one). Models are injected, so tests use fakes.
    EmbeddingDrift   1 - cosine of a multilingual encoder (LaBSE): a size only
    NLIDrift         bidirectional entailment with a cross-lingual NLI model: does the source imply the rendering,
                     and the rendering the source? Both: equivalent; one way: narrower or broader; neither: shifted;
                     contradiction either way: contradicted. Size: 1 - the mean of the two entailment probabilities.
"""
from src.drift.types import BROADER, CONTRADICTED, EQUIVALENT, NARROWER, SHIFTED, Drift

NLI_MODEL = 'MoritzLaurer/mDeBERTa-v3-base-xnli-multilingual-nli-2mil7'   # ~1 GB, 100 languages, zh-en included
ENTAILS = 0.5        # an entailment probability at least this counts as "implies"
CONTRADICTS = 0.5


class EmbeddingDrift:
    name = 'embedding'

    def __init__(self, encode):
        self.encode = encode          # list[str] -> unit vectors

    def score(self, source, rendering):
        a, b = self.encode([source, rendering])
        similarity = float(a @ b)
        return Drift(round(1 - similarity, 3), None, self.name, {'similarity': round(similarity, 3)})


class NLIDrift:
    name = 'nli'

    def __init__(self, nli=None):
        self.nli = nli or load_nli()   # (premise, hypothesis) -> {'entailment', 'neutral', 'contradiction'} probs

    def score(self, source, rendering):
        forward, backward = self.nli(source, rendering), self.nli(rendering, source)
        implies, implied = forward['entailment'] >= ENTAILS, backward['entailment'] >= ENTAILS
        if max(forward['contradiction'], backward['contradiction']) >= CONTRADICTS:
            kind = CONTRADICTED
        elif implies and implied:
            kind = EQUIVALENT
        elif implies:
            kind = BROADER
        elif implied:
            kind = NARROWER
        else:
            kind = SHIFTED
        size = 1 - (forward['entailment'] + backward['entailment']) / 2
        return Drift(round(size, 3), kind, self.name,
                     {'source_implies': {k: round(v, 3) for k, v in forward.items()},
                      'rendering_implies': {k: round(v, 3) for k, v in backward.items()}})


def load_nli(model_name=NLI_MODEL):
    """A cross-lingual NLI function: (premise, hypothesis) -> probabilities by label (downloaded once)."""
    import torch
    from transformers import AutoModelForSequenceClassification, AutoTokenizer
    tokenizer = AutoTokenizer.from_pretrained(model_name)
    model = AutoModelForSequenceClassification.from_pretrained(model_name).eval()
    labels = {i: name.lower() for i, name in model.config.id2label.items()}

    def nli(premise, hypothesis):
        inputs = tokenizer(premise, hypothesis, truncation=True, return_tensors='pt')
        with torch.no_grad():
            probs = torch.softmax(model(**inputs).logits[0], dim=-1).tolist()
        return {labels[i]: p for i, p in enumerate(probs)}
    return nli
