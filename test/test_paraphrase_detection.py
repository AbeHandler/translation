"""Run from the repo root: python -m pytest test/"""
from src.paraphrase_detection.polnear import parse_ann, read_split, tag_article
from src.paraphrase_detection.predict import group
from src.token_tagging.tagger import chunk_bounds

TEXT = 'Title\n\nOfficials said the talks would resume. "We are ready," Smith said.\n\nHe thinks she believes it.'
ANN = '\n'.join([
    'T1\tSource 7 16\tOfficials', 'T2\tCue 17 21\tsaid', 'T3\tContent 22 45\tthe talks would resume.',
    'E1\tAttribution:T9 Source:T1 Cue:T2 Content:T3',
    'T4\tContent 46 61\t"We are ready,"', 'T5\tSource 62 67\tSmith', 'T6\tCue 68 72\tsaid',
    'E2\tAttribution:T9 Content:T4 Source:T5 Cue:T6',
    'T7\tSource 75 77\tHe', 'T8\tCue 78 84\tthinks', 'T10\tContent 85 101\tshe believes it.',
    'E3\tAttribution:T9 Source:T7 Cue:T8 Content:T10',
    'T11\tSource 85 88\tshe', 'T12\tCue 89 97\tbelieves', 'T13\tContent 98 100\tit',
    'E4\tAttribution:T9 Source:T11 Cue:T12 Content:T13',
    '#1\tAnnotatorNotes T1\ta note',
])


def test_tags_skip_direct_quotes_and_nested_attributions():
    title, first, second = (p for p in tag_article(TEXT, parse_ann(ANN))[0])
    assert set(title.tags) == {'Out'}
    assert list(zip(first.words, first.tags))[:4] == [
        ('Officials', 'B-Source'), ('said', 'B-Cue'), ('the', 'B-Content'), ('talks', 'I-Content')]
    assert set(first.tags[first.words.index('"'):]) == {'Out'}  # the direct quote and its speaker
    assert second.tags == ['B-Source', 'B-Cue', 'B-Content', 'I-Content', 'I-Content', 'I-Content']
    _, counts = tag_article(TEXT, parse_ann(ANN))
    assert (counts['tagged'], counts['direct_quotes'], counts['nested']) == (2, 1, 1)


def test_read_split_uses_the_first_annotator(tmp_path):
    for sub in ('text', 'attributions'):
        (tmp_path / 'train' / sub).mkdir(parents=True)
    (tmp_path / 'train' / 'text' / 'a.txt').write_text(TEXT, encoding='utf-8')
    (tmp_path / 'train' / 'attributions' / 'a_bbbb.ann').write_text('', encoding='utf-8')
    (tmp_path / 'train' / 'attributions' / 'a_aaaa.ann').write_text(ANN, encoding='utf-8')
    paragraphs, counts = read_split(tmp_path, 'train')
    assert len(paragraphs) == 3 and counts['articles'] == 1 and counts['tagged'] == 2


def test_group_pairs_content_with_nearest_cue_and_its_source():
    spans = [('Source', 0, 0), ('Cue', 1, 1), ('Content', 2, 5), ('Content', 10, 12), ('Cue', 13, 13),
             ('Source', 14, 15)]
    assert group(spans) == [(('Content', 2, 5), ('Cue', 1, 1), ('Source', 0, 0)),
                            (('Content', 10, 12), ('Cue', 13, 13), ('Source', 14, 15))]
    assert group([('Content', 0, 3)]) == [(('Content', 0, 3), None, None)]


def test_chunks_end_at_sentence_ends_when_they_can():
    words = ['a', 'b', '.', 'c', 'd', 'e', 'f', '.', 'g']
    assert chunk_bounds(words, 5) == [(0, 3), (3, 8), (8, 9)]
    assert chunk_bounds(['a'] * 7, 3) == [(0, 3), (3, 6), (6, 7)]
    assert chunk_bounds(words, None) == [(0, 9)]
