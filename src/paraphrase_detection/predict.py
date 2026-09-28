"""
ParaphraseDetector: raw text -> attributions (content, cue, source), from a model trained by
scripts/train_paraphrase_detector.py. Words and spans come from src/token_tagging/tagger.py.

Tags don't say which Source and Cue go with which Content, so within a paragraph each Content is paired with the
nearest Cue, and that Cue with the nearest Source (either side, fewest words between). Contents with no Cue in the
paragraph get none, and no Source.

    detector = ParaphraseDetector('results/train_paraphrase_detector/electra_small/model')
    detector.predict('Officials said the talks would resume next week.')
"""
from src.token_tagging.tagger import WordTagger

FIELDS = ('content', 'cue', 'source')


def gap(a, b):
    """Words between two (type, first, last) spans; 0 when adjacent or overlapping."""
    return max(a[1] - b[2], b[1] - a[2], 1) - 1


def nearest(span, candidates):
    return min(candidates, key=lambda c: gap(span, c), default=None)


def group(span_list):
    """[(content, cue, source)] per Content span; cue and source may be None."""
    by_type = {kind: [s for s in span_list if s[0] == kind] for kind in ('Content', 'Cue', 'Source')}
    groups = []
    for content in by_type['Content']:
        cue = nearest(content, by_type['Cue'])
        source = nearest(cue, by_type['Source']) if cue else None
        groups.append((content, cue, source))
    return groups


class ParaphraseDetector:
    def __init__(self, model_dir, max_length=512, device=None):
        self.tagger = WordTagger(model_dir, max_length, device)

    def predict(self, text):
        """[{content, cue, source, content_start, content_end, cue_start, ...}], character offsets into text
        (cue and source fields None when there is none)."""
        results = []
        for paragraph, base, words, span_list in self.tagger.tagged_paragraphs(text):
            for spans in group(span_list):
                row = {}
                for field, span in zip(FIELDS, spans):
                    start, end = (words[span[1]][1], words[span[2]][2]) if span else (None, None)
                    row[field] = paragraph[start:end] if span else None
                    row[f'{field}_start'] = base + start if span else None
                    row[f'{field}_end'] = base + end if span else None
                results.append(row)
        return results


def predict(text, model_dir):
    """One-off convenience; build a ParaphraseDetector once to predict many texts."""
    return ParaphraseDetector(model_dir).predict(text)
