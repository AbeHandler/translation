"""
QuoteExtractor: raw text -> direct quotations with their speakers, from a model trained by
scripts/train_quote_extractor.py. Words and spans come from src/token_tagging/tagger.py. A LeftSpeaker quotation
is attributed to the nearest Speaker before it in the paragraph, a RightSpeaker one to the nearest after it;
Unknown quotations have no speaker.

    extractor = QuoteExtractor('results/train_quote_extractor/electra_small/model')
    extractor.predict('"We will keep going," said Liang Wenfeng.')
"""
from src.token_tagging.tagger import WordTagger

QUOTE_TYPES = ('LeftSpeaker', 'RightSpeaker', 'Unknown')


def attribute(span_list):
    """Pair each quotation with its speaker span (or None), per the quotation's type."""
    speakers = [s for s in span_list if s[0] == 'Speaker']
    pairs = []
    for kind, first, last in span_list:
        if kind not in QUOTE_TYPES:
            continue
        speaker = None
        if kind == 'LeftSpeaker':
            speaker = max((s for s in speakers if s[2] < first), key=lambda s: s[2], default=None)
        elif kind == 'RightSpeaker':
            speaker = min((s for s in speakers if s[1] > last), key=lambda s: s[1], default=None)
        pairs.append(((kind, first, last), speaker))
    return pairs


class QuoteExtractor:
    def __init__(self, model_dir, max_length=256, device=None):
        self.tagger = WordTagger(model_dir, max_length, device)

    def predict(self, text):
        """[{quote, quote_type, speaker, quote_start, quote_end, speaker_start, speaker_end}], character offsets
        into text (speaker fields None when there is none)."""
        results = []
        for paragraph, base, words, span_list in self.tagger.tagged_paragraphs(text):
            for (kind, first, last), speaker in attribute(span_list):
                row = {'quote': paragraph[words[first][1]:words[last][2]], 'quote_type': kind,
                       'quote_start': base + words[first][1], 'quote_end': base + words[last][2],
                       'speaker': None, 'speaker_start': None, 'speaker_end': None}
                if speaker:
                    _, s_first, s_last = speaker
                    row.update(speaker=paragraph[words[s_first][1]:words[s_last][2]],
                               speaker_start=base + words[s_first][1], speaker_end=base + words[s_last][2])
                results.append(row)
        return results


def predict(text, model_dir):
    """One-off convenience; build a QuoteExtractor once to predict many texts."""
    return QuoteExtractor(model_dir).predict(text)
