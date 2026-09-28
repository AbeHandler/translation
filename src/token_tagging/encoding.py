"""Labels and subword alignment: a word's tag goes on its first subword; the rest, and special tokens, get -100
(ignored by the loss and the metrics)."""
IGNORE = -100


def label_list(paragraphs):
    """Every tag in the data, 'Out' first, then B-/I- pairs by type."""
    types = sorted({tag[2:] for p in paragraphs for tag in p.tags if tag != 'Out'})
    return ['Out'] + [f'{prefix}-{t}' for t in types for prefix in ('B', 'I')]


def encode(paragraphs, tokenizer, label2id, max_length):
    """Tokenized paragraphs with aligned labels, as a dict of lists (for datasets.Dataset.from_dict). Paragraphs
    longer than max_length subwords are truncated. Returns (encoded, number truncated)."""
    encoded = tokenizer([p.words for p in paragraphs], is_split_into_words=True, truncation=True,
                        max_length=max_length)
    labels, n_truncated = [], 0
    for i, paragraph in enumerate(paragraphs):
        word_ids = encoded.word_ids(i)
        previous, row = None, []
        for word_id in word_ids:
            row.append(IGNORE if word_id is None or word_id == previous else label2id[paragraph.tags[word_id]])
            previous = word_id
        labels.append(row)
        n_truncated += max(w for w in word_ids if w is not None) + 1 < len(paragraph.words)
    return {**encoded, 'labels': labels}, n_truncated
