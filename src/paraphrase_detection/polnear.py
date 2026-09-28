"""
Reading PolNeAR: <split>/text/<article>.txt and <split>/attributions/<article>_<annotator>.ann (brat standoff).

In a .ann file, T lines are labeled character spans (fragments separated by ';' when discontinuous):
    T1	Source 110 112	we
and E lines tie them into one attribution:
    E1	Attribution:T4 Content:T3 Cue:T2 Source:T1
An attribution can have no Source, and more than one Content. Some articles were annotated by several
annotators; the first .ann file in sorted order is used.

Articles are split into paragraphs and words as at prediction time (src/token_tagging/tagger.py), paragraphs into
chunks of at most MAX_WORDS words, and each word is tagged B-/I- Source, Cue or Content. Two kinds of
attributions are left untagged:
  - direct quotes: every Content is wrapped in quotation marks (src/quote_extraction covers those)
  - nested: an attribution whose spans overlap a longer one already tagged ("He said [she claimed X]" keeps the
    outer one; one tag per word can't hold both)
"""
from collections import Counter
from pathlib import Path

from src.token_tagging.data import OUT, Paragraph, to_iob2
from src.token_tagging.tagger import chunk_bounds, paragraphs, words_with_offsets

ROLES = ('Source', 'Cue', 'Content')
QUOTE_MARKS = '"“”'
TRAILING_PUNCTUATION = '.,;:!?'
MAX_WORDS = 150  # 99% of PolNeAR paragraphs are shorter; some articles have no paragraph breaks at all


def parse_ann(ann_text):
    """[[(role, [(start, end), ...]), ...] per attribution]. Roles other than Source/Cue/Content* are dropped;
    Content2, Content3... become Content."""
    fragments, events = {}, []
    for line in ann_text.splitlines():
        parts = line.split('\t')
        if line.startswith('T') and len(parts) >= 2:
            label, _, offsets = parts[1].partition(' ')
            fragments[parts[0]] = [tuple(map(int, piece.split())) for piece in offsets.split(';')]
        elif line.startswith('E') and len(parts) >= 2:
            events.append([arg.split(':', 1) for arg in parts[1].split()])
    attributions = []
    for args in events:
        spans = [(role.rstrip('0123456789'), fragments[t]) for role, t in args
                 if role.rstrip('0123456789') in ROLES and t in fragments]
        if spans:
            attributions.append(spans)
    return attributions


def is_direct_quote(attribution, text):
    """True when every Content is wrapped in quotation marks (trailing punctuation aside)."""
    contents = [' '.join(text[s:e] for s, e in pieces).strip().rstrip(TRAILING_PUNCTUATION)
                for role, pieces in attribution if role == 'Content']
    return bool(contents) and all(c[:1] in QUOTE_MARKS and c[-1:] in QUOTE_MARKS for c in contents)


def extent(attribution):
    starts_ends = [x for _, pieces in attribution for piece in pieces for x in piece]
    return max(starts_ends) - min(starts_ends)


def word_range(word_starts, start, end):
    """(first, last) index of the words starting in [start, end), or None."""
    inside = [i for i, s in enumerate(word_starts) if start <= s < end]
    return (inside[0], inside[-1]) if inside else None


def tag_article(text, attributions, max_words=MAX_WORDS):
    """(paragraphs, counts): Paragraph per text paragraph chunk, tags from the non-direct, non-nested
    attributions."""
    counts = Counter(attributions=len(attributions))
    words, paragraph_of = [], []
    for n, (paragraph, base) in enumerate(paragraphs(text)):
        for word, start, end in words_with_offsets(paragraph):
            words.append((word, base + start))
            paragraph_of.append(n)
    word_starts = [start for _, start in words]
    tags, tagged = [OUT] * len(words), {}  # tagged: (first, last) -> role
    for attribution in sorted(attributions, key=extent, reverse=True):
        if is_direct_quote(attribution, text):
            counts['direct_quotes'] += 1
            continue
        ranges = [(role, r) for role, pieces in attribution for s, e in pieces
                  if (r := word_range(word_starts, s, e))]
        new = [(role, r) for role, r in ranges if tagged.get(r) != role]  # a span shared with a tagged one is fine
        if any(tags[i] != OUT for _, (first, last) in new for i in range(first, last + 1)):
            counts['nested'] += 1
            continue
        for role, (first, last) in new:
            tagged[(first, last)] = role
            tags[first:last + 1] = [f'B-{role}'] + [f'I-{role}'] * (last - first)
        counts['tagged'] += 1
    by_paragraph = {}
    for (word, _), tag, n in zip(words, tags, paragraph_of):
        by_paragraph.setdefault(n, Paragraph([], []))
        by_paragraph[n].words.append(word)
        by_paragraph[n].tags.append(tag)
    result = [Paragraph(p.words[start:end], to_iob2(p.tags[start:end]))
              for _, p in sorted(by_paragraph.items()) for start, end in chunk_bounds(p.words, max_words)]
    return result, counts


def annotation_path(split_dir, stem):
    """The article's first .ann file in sorted order. Raises if there is none."""
    found = sorted((split_dir / 'attributions').glob(f'{stem}_*.ann'))
    if not found:
        raise FileNotFoundError(f'no attributions for {split_dir / "text" / stem}.txt')
    return found[0]


def read_split(data_dir, split, max_articles=None, max_words=MAX_WORDS):
    """(paragraphs, counts) for PolNeAR's data/<split> (train, dev or test), articles in sorted order."""
    split_dir = Path(data_dir) / split
    texts = sorted((split_dir / 'text').glob('*.txt'))[:max_articles]
    if not texts:
        raise FileNotFoundError(f'no articles in {split_dir / "text"}')
    all_paragraphs, counts = [], Counter()
    for path in texts:
        text = path.read_text(encoding='utf-8')
        ann = annotation_path(split_dir, path.stem).read_text(encoding='utf-8')
        article_paragraphs, article_counts = tag_article(text, parse_ann(ann), max_words)
        all_paragraphs.extend(article_paragraphs)
        counts.update(article_counts)
    counts['articles'] = len(texts)
    return all_paragraphs, dict(counts)
