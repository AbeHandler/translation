"""Sentences, and where the focal phrase occurs in the source."""
import re

from src.dispersion.types import Focal, Sentence, Span

EN_END = re.compile(r'(?<=[.!?])["”’)\]]?\s+')
ZH_END = re.compile(r'(?<=[。！？!?])[”’」』）]?')


def sentences(text, lang):
    """The text's sentences with their offsets; also split at line breaks."""
    pattern = ZH_END if lang == 'zh' else EN_END
    out = []
    for line in re.finditer(r'[^\n]+', text):
        cuts = [m.end() for m in pattern.finditer(line.group())] + [len(line.group())]
        prev = 0
        for cut in cuts:
            piece = line.group()[prev:cut]
            stripped = piece.strip()
            if stripped:
                begin = line.start() + prev + piece.index(stripped)
                out.append(Sentence(stripped, (begin, begin + len(stripped))))
            prev = cut
    return out


def occurrences(focal: Focal, text):
    """The focal phrase's spans in the source: the given span, or every match of its text (English: case-
    insensitive, whole words; Chinese: anywhere)."""
    if focal.span:
        return [focal.span]
    if focal.lang == 'zh':
        pattern = re.escape(focal.text)
    else:
        pattern = r'(?<![A-Za-z])' + re.escape(focal.text) + r'(?![A-Za-z])'
    return [(m.start(), m.end()) for m in re.finditer(pattern, text, re.IGNORECASE)]


def sentence_of(span: Span, sents):
    return next((s for s in sents if s.span[0] <= span[0] and span[1] <= s.span[1]), None)
