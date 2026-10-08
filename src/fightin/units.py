"""
The units Fightin' Words counts in each document: words, or n-grams (phrases), cleaned so that English and Chinese
documents can be compared (see src/fightin/concepts.py for why):
    English   Latin-script words, lowercased
    Chinese   Chinese words, and Latin-script words with a capital (names, acronyms: AI, OpenAI, GPT-4o); all-lowercase
              Latin words are quoted English text and left out
Numbers, punctuation and left-out words break the text into runs; n-grams never cross a break. A phrase's first and
last words must carry content: in English not a stopword, one letter or less; in Chinese not a single character
(的, 在, 是, 了 ...), or a capitalised Latin name. Interior words can be anything ("department of war", 人工智能的发展).
English phrases are joined by spaces, Chinese ones without.
"""
import re

from src.fightin.concepts import LATIN, normalise

CJK = re.compile('[一-鿿]')


def runs(raw_tokens, lang):
    """The document's kept words (normalised), split into runs at breaks."""
    out, run = [], []
    for raw in raw_tokens:
        word = normalise(raw)
        latin = bool(word) and bool(LATIN.match(word))
        kept = bool(word) and (latin if lang == 'en' else not (latin and raw.islower()))
        if kept:
            run.append(word)
        elif run:
            out.append(run)
            run = []
    return out + ([run] if run else [])


def is_edge(word, lang, stopwords):
    if lang == 'en':
        return len(word) > 1 and word not in stopwords
    return bool(LATIN.match(word)) or (bool(CJK.search(word)) and len(word) > 1)


def units(raw_tokens, lang, ns=(1,), stopwords=frozenset()):
    """The document's units: words when n is 1 (all kept words: stopword concepts are dropped later, after Chinese
    words are mapped), n-grams with content words at both ends otherwise."""
    out = []
    for run in runs(raw_tokens, lang):
        for n in ns:
            if n == 1:
                out += run
                continue
            for k in range(len(run) - n + 1):
                gram = run[k:k + n]
                if is_edge(gram[0], lang, stopwords) and is_edge(gram[-1], lang, stopwords):
                    out.append(join(gram, lang))
    return out


def join(words, lang):
    """English words with spaces; Chinese without, except between two Latin words (OpenAI GPT-5)."""
    if lang == 'en':
        return ' '.join(words)
    out = words[0]
    for prev, word in zip(words, words[1:]):
        out += (' ' if LATIN.match(prev) and LATIN.match(word) else '') + word
    return out


def parse_ns(spec):
    """'1' -> (1,); '2-3' -> (2, 3)."""
    low, _, high = str(spec).partition('-')
    return tuple(range(int(low), int(high or low) + 1))
