"""The data model. Spans are (start, end) character offsets, end exclusive; a rendering is a list of spans, since
a target language can split a phrase around other words (AI governance -> 人工智能的全球治理: 人工智能 ... 治理)."""
from dataclasses import dataclass, field
from typing import Optional

Span = tuple[int, int]

RENDERED, DROPPED, NOT_FOUND = 'rendered', 'dropped', 'not_found'


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
    status: str                                    # RENDERED, DROPPED (its sentence crossed, it didn't), NOT_FOUND
    target_spans: list[Span] = field(default_factory=list)   # in the target document; [] unless RENDERED
    target_text: str = ''                          # the pieces joined with '…'
    score: float = 0.0
    method: str = ''
    source_sentence: Optional[Sentence] = None
    target_sentence: Optional[Sentence] = None
    sentence_score: float = 0.0
