"""The data model. Spans are (start, end) character offsets, end exclusive; a rendering is a list of spans, since
a target language can split a phrase around other words (AI governance -> 人工智能的全球治理: 人工智能 ... 治理)."""
from dataclasses import dataclass, field
from typing import Optional

Span = tuple[int, int]

# uptake: how a focal span (a phrase or a whole sentence) crosses into the target
VERBATIM, TRANSLATED, PARAPHRASED, DROPPED = 'verbatim', 'translated', 'paraphrased', 'dropped'
RENDERINGS = (VERBATIM, TRANSLATED, PARAPHRASED)     # the uptakes with a counterpart span in the target


@dataclass(frozen=True)
class Doc:
    id: str
    lang: str          # 'en' or 'zh'
    text: str


@dataclass(frozen=True)
class Focal:
    text: str                      # the phrase, e.g. "governance" or 治理
    lang: str
    span: Optional[Span] = None    # one occurrence in the source; None: every occurrence of text


@dataclass(frozen=True)
class Sentence:
    text: str
    span: Span                     # where it sits in its document


@dataclass
class Prediction:
    focal_span: Span                               # the occurrence in the source
    uptake: str                                    # VERBATIM, TRANSLATED, PARAPHRASED or DROPPED
    # reason: same text, known rendering, similarity, or for DROPPED: no sentence, no span (nothing aligned),
    # dissimilar (aligned, but not close in meaning)
    reason: str = ''
    # the counterpart in the target (also kept for DROPPED 'dissimilar', to inspect)
    target_spans: list[Span] = field(default_factory=list)
    target_text: str = ''                          # the pieces joined with '…'
    span_score: float = 0.0                        # similarity of the focal span and its counterpart
    sentence_score: float = 0.0                    # similarity of their sentences
    level: str = 'phrase'                          # 'phrase', or 'sentence' when the focal span is a whole sentence
    method: str = ''                               # the phrase aligner
    source_sentence: Optional[Sentence] = None
    target_sentence: Optional[Sentence] = None
