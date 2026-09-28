"""A paragraph of words with one IOB2 tag each, the unit every tagger trains and predicts on."""
from dataclasses import dataclass

OUT = 'Out'


@dataclass
class Paragraph:
    words: list
    tags: list


def label_type(tag):
    return None if tag == OUT else tag.split('-', 1)[1]


def to_iob2(tags):
    """I-X that starts a chunk (after Out or another type) becomes B-X."""
    fixed = []
    for i, tag in enumerate(tags):
        if tag.startswith('I-') and (i == 0 or label_type(tags[i - 1]) != label_type(tag)):
            tag = 'B-' + tag[2:]
        fixed.append(tag)
    return fixed
