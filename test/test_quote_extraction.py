"""Run from the repo root: python -m pytest test/"""
from src.quote_extraction.data import read_conll, split_contiguous
from src.quote_extraction.predict import attribute
from src.token_tagging.data import Paragraph, to_iob2
from src.token_tagging.encoding import label_list
from src.token_tagging.tagger import spans, words_with_offsets


def test_read_conll_normalizes_chunk_starts_to_b(tmp_path):
    (tmp_path / 'd.txt').write_text('" I-LeftSpeaker\nHi I-LeftSpeaker\n" I-LeftSpeaker\nsaid Out\nhe B-Speaker\n\n'
                                    'x Out\n', encoding='utf-8')
    first, second = read_conll(tmp_path / 'd.txt')
    assert first.tags == ['B-LeftSpeaker', 'I-LeftSpeaker', 'I-LeftSpeaker', 'Out', 'B-Speaker']
    assert second.words == ['x']
    assert to_iob2(['I-Speaker', 'I-Unknown']) == ['B-Speaker', 'B-Unknown']


def test_contiguous_split_and_labels():
    paragraphs = [Paragraph(['w'], ['B-Speaker' if i % 2 else 'Out']) for i in range(10)]
    split = split_contiguous(paragraphs, 0.8, 0.1)
    assert [len(split[k]) for k in ('train', 'dev', 'test')] == [8, 1, 1] and split['test'][0] is paragraphs[9]
    assert label_list(paragraphs) == ['Out', 'B-Speaker', 'I-Speaker']


def test_spans_and_attribution_follow_the_quote_type():
    text = 'Yang said " we grow " and " we win , " added Liang Wenfeng'
    words = [w for w, _, _ in words_with_offsets(text)]
    tags = ['B-Speaker', 'Out', 'B-LeftSpeaker', 'I-LeftSpeaker', 'I-LeftSpeaker', 'I-LeftSpeaker', 'Out',
            'B-RightSpeaker', 'I-RightSpeaker', 'I-RightSpeaker', 'I-RightSpeaker', 'I-RightSpeaker', 'Out',
            'B-Speaker', 'I-Speaker']
    assert len(words) == len(tags)
    found = spans(tags)
    assert found[0] == ('Speaker', 0, 0) and found[-1] == ('Speaker', 13, 14)
    (left, left_speaker), (right, right_speaker) = attribute(found)
    assert left_speaker == ('Speaker', 0, 0) and right_speaker == ('Speaker', 13, 14)
