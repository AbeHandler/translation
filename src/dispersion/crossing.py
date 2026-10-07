"""
PhraseCrossingDetector: how a focal span in a source document crosses into a target document. The focal span is a
phrase ("governance", 治理) or a whole sentence; its uptake in the target is one of
    verbatim      the target has the same text (an English term kept in Chinese: Claude, AGI)
    translated    the target has a counterpart span close in meaning
    paraphrased   a counterpart span looser in meaning
    dropped       no counterpart: no target sentence matches its sentence, nothing aligns to it within the matched
                  sentence, or what aligns isn't close in meaning
The counterpart: for a sentence, the best-matching target sentence (SentenceMatcher); for a phrase, the span a
phrase aligner finds within that sentence. Closeness: the encoder's similarity of the focal span and its
counterpart, against cut-offs per level (single words score differently from sentences), or a known rendering
(agents -> 智能体, which the encoder scores low). The cut-offs are provisional, to be set on a gold set.
"""
import re

from src.dispersion.dispersion import normalise
from src.dispersion.locate import occurrences, sentence_of, sentences
from src.dispersion.types import DROPPED, PARAPHRASED, TRANSLATED, VERBATIM, Prediction

# (translated at or above, paraphrased at or above): LaBSE on single words and phrases runs lower than on sentences
CUTOFFS = {'sentence': (0.75, 0.60), 'phrase': (0.60, 0.45)}


class PhraseCrossingDetector:
    def __init__(self, matcher, aligner, encode, known=None, cutoffs=CUTOFFS):
        """matcher: SentenceMatcher (its min_score is the floor below which a sentence has no counterpart);
        aligner: a phrase aligner (src/dispersion/aligners); encode: list[str] -> unit vectors (LaBSE);
        known: {focal text: [renderings counted as translations]}."""
        self.matcher, self.aligner, self.encode, self.cutoffs = matcher, aligner, encode, cutoffs
        self.known = {k.lower(): {normalise(r) for r in v} for k, v in (known or {}).items()}

    def detect(self, focal, source, target):
        """[Prediction], one per occurrence of the focal span in the source."""
        source_sents, target_sents = sentences(source.text, source.lang), sentences(target.text, target.lang)
        return [self._one(focal, span, source, target, source_sents, target_sents)
                for span in occurrences(focal, source.text)]

    def _one(self, focal, span, source, target, source_sents, target_sents):
        src = sentence_of(span, source_sents)
        level = 'sentence' if src and (span[0], span[1]) == src.span else 'phrase'
        base = {'level': level, 'method': self.aligner.name, 'source_sentence': src}
        matches = self.matcher.match(src, target_sents) if src else []
        if not matches:
            return Prediction(span, DROPPED, 'no sentence', **base)
        tgt, sentence_score = matches[0]
        base.update(target_sentence=tgt, sentence_score=sentence_score)
        if level == 'sentence':
            return Prediction(span, self._label(sentence_score, 'sentence'), 'similarity', [tgt.span], tgt.text,
                              sentence_score, **base)
        text = source.text[span[0]:span[1]]
        same = self._same_text(text, tgt)
        if same:
            return Prediction(span, VERBATIM, 'same text', [same], target.text[same[0]:same[1]], 1.0, **base)
        pieces, _ = self.aligner.align((span[0] - src.span[0], span[1] - src.span[0]), src.text, tgt.text)
        if not pieces:
            return Prediction(span, DROPPED, 'no span', **base)
        spans = [(tgt.span[0] + a, tgt.span[0] + b) for a, b in pieces]
        rendering = '…'.join(target.text[a:b] for a, b in spans)
        if normalise(rendering) in self.known.get(text.lower(), ()):
            return Prediction(span, TRANSLATED, 'known rendering', spans, rendering, 1.0, **base)
        vectors = self.encode([text, rendering.replace('…', ' ')])
        score = float(vectors[0] @ vectors[1])
        uptake = self._label(score, 'phrase')
        return Prediction(span, uptake, 'similarity' if uptake != DROPPED else 'dissimilar', spans, rendering, score,
                          **base)

    def _label(self, score, level):
        translated, paraphrased = self.cutoffs[level]
        return TRANSLATED if score >= translated else PARAPHRASED if score >= paraphrased else DROPPED

    @staticmethod
    def _same_text(text, tgt):
        """The span of the focal text in the target sentence, as is (case-insensitive; Latin as a whole word)."""
        pattern = re.escape(text) if not re.search('[A-Za-z]', text) else \
            r'(?<![A-Za-z])' + re.escape(text) + r'(?![A-Za-z])'
        m = re.search(pattern, tgt.text, re.IGNORECASE)
        return (tgt.span[0] + m.start(), tgt.span[0] + m.end()) if m else None
