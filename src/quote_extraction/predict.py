"""
QuoteExtractor: raw text -> direct quotations with their speakers, from a model trained by training.py.

Text is split into paragraphs on blank lines and into words the way DirectQuote is tokenized (words, and each
punctuation mark on its own, so "Trump's" -> Trump ' s). Each word gets its first subword's tag; tagged words
are joined into spans. A LeftSpeaker quotation is attributed to the nearest Speaker before it in the paragraph,
a RightSpeaker one to the nearest after it; Unknown quotations have no speaker.

    extractor = QuoteExtractor('results/train_quote_extractor/electra_small/model')
    extractor.predict('"We will keep going," said Liang Wenfeng.')
"""
import re

import torch
from transformers import AutoModelForTokenClassification, AutoTokenizer

WORD = re.compile(r'\w+|[^\w\s]')
QUOTE_TYPES = ('LeftSpeaker', 'RightSpeaker', 'Unknown')


def words_with_offsets(paragraph):
    return [(m.group(0), m.start(), m.end()) for m in WORD.finditer(paragraph)]


def spans(tags):
    """[(type, first word, last word)] from IOB2 tags, lenient: an I- after another type starts a span too."""
    found = []
    for i, tag in enumerate(tags):
        if tag == 'Out':
            continue
        kind = tag[2:]
        if tag.startswith('B-') or not found or found[-1][0] != kind or found[-1][2] != i - 1:
            found.append([kind, i, i])
        else:
            found[-1][2] = i
    return [tuple(span) for span in found]


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
        self.tokenizer = AutoTokenizer.from_pretrained(model_dir)
        self.model = AutoModelForTokenClassification.from_pretrained(model_dir).eval()
        self.device = device or ('mps' if torch.backends.mps.is_available() else
                                 'cuda' if torch.cuda.is_available() else 'cpu')
        self.model.to(self.device)
        self.max_length = max_length

    def word_tags(self, words):
        """One tag per word (words past max_length subwords get 'Out')."""
        encoded = self.tokenizer(words, is_split_into_words=True, truncation=True, max_length=self.max_length,
                                 return_tensors='pt')
        with torch.no_grad():
            logits = self.model(**{k: v.to(self.device) for k, v in encoded.items()}).logits[0]
        predicted = logits.argmax(-1).tolist()
        tags, seen = ['Out'] * len(words), set()
        for position, word_id in enumerate(encoded.word_ids(0)):
            if word_id is not None and word_id not in seen:
                seen.add(word_id)
                tags[word_id] = self.model.config.id2label[predicted[position]]
        return tags

    def predict(self, text):
        """[{quote, quote_type, speaker, quote_start, quote_end, speaker_start, speaker_end}], character offsets
        into text (speaker fields None when there is none)."""
        results = []
        for match in re.finditer(r'[^\n]+(?:\n(?!\s*\n)[^\n]+)*', text):  # paragraphs: split on blank lines
            paragraph, base = match.group(0), match.start()
            words = words_with_offsets(paragraph)
            if not words:
                continue
            tags = self.word_tags([w for w, _, _ in words])
            for (kind, first, last), speaker in attribute(spans(tags)):
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
