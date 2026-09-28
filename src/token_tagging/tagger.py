"""
Raw text -> paragraphs and words, and a trained model's tags for them.

Paragraphs are split on blank lines. Words are split the way DirectQuote is tokenized: words, and each
punctuation mark on its own ("Trump's" -> Trump ' s). Training readers split text the same way, so the model sees
the same units at prediction time. Each word gets its first subword's tag; spans() joins tagged words. Long
paragraphs can be cut into chunks of at most max_words (chunk_bounds), in training and prediction alike.
"""
import re

import torch
from transformers import AutoModelForTokenClassification, AutoTokenizer

from src.token_tagging.data import OUT

WORD = re.compile(r'\w+|[^\w\s]')
PARAGRAPH = re.compile(r'[^\n]+(?:\n(?!\s*\n)[^\n]+)*')
SENTENCE_END = {'.', '?', '!'}


def paragraphs(text):
    """[(paragraph, offset of its first character in text)]"""
    return [(m.group(0), m.start()) for m in PARAGRAPH.finditer(text)]


def chunk_bounds(words, max_words):
    """[(start, end)] covering words in order, each at most max_words long and cut after the window's last sentence
    end when it has one. max_words None: one chunk."""
    if max_words is None or len(words) <= max_words:
        return [(0, len(words))]
    bounds, start = [], 0
    while start < len(words):
        end = min(start + max_words, len(words))
        if end < len(words):
            end = max((i + 1 for i in range(start, end) if words[i] in SENTENCE_END), default=end)
        bounds.append((start, end))
        start = end
    return bounds


def words_with_offsets(paragraph):
    return [(m.group(0), m.start(), m.end()) for m in WORD.finditer(paragraph)]


def spans(tags):
    """[(type, first word, last word)] from IOB2 tags, lenient: an I- after another type starts a span too."""
    found = []
    for i, tag in enumerate(tags):
        if tag == OUT:
            continue
        kind = tag[2:]
        if tag.startswith('B-') or not found or found[-1][0] != kind or found[-1][2] != i - 1:
            found.append([kind, i, i])
        else:
            found[-1][2] = i
    return [tuple(span) for span in found]


class WordTagger:
    def __init__(self, model_dir, max_length=256, device=None, max_words=None):
        self.tokenizer = AutoTokenizer.from_pretrained(model_dir)
        self.model = AutoModelForTokenClassification.from_pretrained(model_dir).eval()
        self.device = device or ('mps' if torch.backends.mps.is_available() else
                                 'cuda' if torch.cuda.is_available() else 'cpu')
        self.model.to(self.device)
        self.max_length = max_length
        self.max_words = max_words

    def word_tags(self, words):
        """One tag per word, tagged max_words at a time (words past max_length subwords of a chunk get 'Out')."""
        return [tag for start, end in chunk_bounds(words, self.max_words) for tag in self.chunk_tags(words[start:end])]

    def chunk_tags(self, words):
        encoded = self.tokenizer(words, is_split_into_words=True, truncation=True, max_length=self.max_length,
                                 return_tensors='pt')
        with torch.no_grad():
            logits = self.model(**{k: v.to(self.device) for k, v in encoded.items()}).logits[0]
        predicted = logits.argmax(-1).tolist()
        tags, seen = [OUT] * len(words), set()
        for position, word_id in enumerate(encoded.word_ids(0)):
            if word_id is not None and word_id not in seen:
                seen.add(word_id)
                tags[word_id] = self.model.config.id2label[predicted[position]]
        return tags

    def tagged_paragraphs(self, text):
        """[(paragraph, offset, words_with_offsets, spans)] for every paragraph with words."""
        results = []
        for paragraph, base in paragraphs(text):
            words = words_with_offsets(paragraph)
            if words:
                results.append((paragraph, base, words, spans(self.word_tags([w for w, _, _ in words]))))
        return results
