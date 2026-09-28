"""Run from the repo root: python -m pytest test/"""
from src.quote_extraction.data import Paragraph, read_conll, split_contiguous, to_iob2
from src.quote_extraction.encoding import label_list
from src.quote_extraction.predict import attribute, spans, words_with_offsets


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


def test_quote_file_has_a_row_per_quote_with_offsets_into_the_ner_text(tmp_path):
    import pyarrow as pa
    import pyarrow.parquet as pq
    from src.ner_html import SCHEMA as NER_SCHEMA
    from src.quote_extraction.pages import QuoteFileWriter

    class FakeExtractor:
        def predict(self, text):
            start = text.index('"') + 1
            end = text.index('"', start)
            return [{'quote': text[start:end], 'quote_type': 'RightSpeaker', 'quote_start': start, 'quote_end': end,
                     'speaker': 'Liang', 'speaker_start': end + 7, 'speaker_end': end + 12}]

    pages = [{'record_id': 'r0', 'url': 'u0', 'language': 'en', 'text': 'T\n"We grow fast," said Liang.',
              'ner_chars': 0, 'entities': None},
             {'record_id': 'r1', 'url': 'u1', 'language': 'zh', 'text': '"中文"', 'ner_chars': 0, 'entities': None}]
    pq.write_table(pa.Table.from_pylist(pages, NER_SCHEMA), tmp_path / 'n.parquet')
    counts = QuoteFileWriter(FakeExtractor(), 'm').write(str(tmp_path / 'n.parquet'), str(tmp_path / 'q.parquet'))
    (row,) = pq.read_table(tmp_path / 'q.parquet').to_pylist()
    assert counts == {'pages': 2, 'pages_with_quotes': 1, 'quotes': 1}
    assert pages[0]['text'][row['quote_start']:row['quote_end']] == row['quote'] == 'We grow fast,'
    assert row['record_id'] == 'r0' and row['n_words'] == 3
