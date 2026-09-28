"""Reading DirectQuote: one word and tag per line, a blank line between paragraphs. The README says IOB1, but the
data marks nearly every chunk start with B- (IOB2); the few chunks that start with I- are fixed to B-."""
from src.token_tagging.data import Paragraph, to_iob2


def read_conll(path):
    """Paragraphs of (words, tags), tags normalized to IOB2. Raises on a line that isn't 'word tag'."""
    paragraphs, words, tags = [], [], []
    with open(path, encoding='utf-8') as f:
        for n, line in enumerate(f, 1):
            line = line.rstrip('\n')
            if not line.strip():
                if words:
                    paragraphs.append(Paragraph(words, to_iob2(tags)))
                    words, tags = [], []
                continue
            parts = line.rsplit(' ', 1)
            if len(parts) != 2 or not parts[0]:
                raise ValueError(f'{path}:{n}: expected "word tag", got {line!r}')
            words.append(parts[0])
            tags.append(parts[1])
    if words:
        paragraphs.append(Paragraph(words, to_iob2(tags)))
    return paragraphs


def split_contiguous(paragraphs, train_frac, dev_frac):
    """Train/dev/test as contiguous blocks in file order. The file has no article ids, and paragraphs of an
    article appear to be adjacent, so blocks keep (nearly all of) an article's paragraphs in one split, where a
    random paragraph split would leak them across splits."""
    n = len(paragraphs)
    n_train, n_dev = int(n * train_frac), int(n * dev_frac)
    return {'train': paragraphs[:n_train], 'dev': paragraphs[n_train:n_train + n_dev],
            'test': paragraphs[n_train + n_dev:]}
