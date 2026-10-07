"""align(focal, source, target): for each occurrence of the focal phrase in the source, its rendering in the target.
    locate      the occurrences and their source sentences
    match       each source sentence's closest target sentence (SentenceMatcher); none: NOT_FOUND
    align       the phrase aligner on that sentence pair: spans -> RENDERED, none -> DROPPED
    map         the spans from sentence to document offsets"""
from src.dispersion.locate import occurrences, sentence_of, sentences
from src.dispersion.types import DROPPED, NOT_FOUND, RENDERED, Prediction


def align(focal, source, target, matcher, aligner):
    """[Prediction], one per occurrence of the focal phrase in the source."""
    source_sents, target_sents = sentences(source.text, source.lang), sentences(target.text, target.lang)
    out = []
    for span in occurrences(focal, source.text):
        src = sentence_of(span, source_sents)
        matches = matcher.match(src, target_sents) if src else []
        if not matches:
            out.append(Prediction(span, NOT_FOUND, method=aligner.name, source_sentence=src))
            continue
        tgt, sentence_score = matches[0]
        pieces, score = aligner.align((span[0] - src.span[0], span[1] - src.span[0]), src.text, tgt.text)
        spans = [(tgt.span[0] + a, tgt.span[0] + b) for a, b in pieces]
        out.append(Prediction(span, RENDERED if spans else DROPPED, spans,
                              '…'.join(target.text[a:b] for a, b in spans), score, aligner.name, src, tgt,
                              sentence_score))
    return out
