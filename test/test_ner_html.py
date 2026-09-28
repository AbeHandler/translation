"""Run from the repo root: python -m pytest test/"""
import pyarrow as pa
import pyarrow.parquet as pq
import spacy

from src.cc_news import ArticleHtmlArchiver
from src.ner_html import EntityExtractor

ARTICLE = ('<html><head><title>Anthropic accuses DeepSeek</title></head><body><article>'
           + '<p>Anthropic said that DeepSeek used Claude to train its models, according to Reuters.</p>' * 5
           + '</article></body></html>').encode('utf-8')


def rule_based_nlp():
    """Stands in for en_core_web_trf: a blank English pipeline that tags two names."""
    nlp = spacy.blank('en')
    nlp.add_pipe('entity_ruler').add_patterns([{'label': 'ORG', 'pattern': 'Anthropic'},
                                               {'label': 'ORG', 'pattern': 'DeepSeek'}])
    nlp.meta.update(name='rules', version='0.0')
    return nlp


def test_entities_per_page_in_order_with_offsets_into_the_stored_text(tmp_path):
    rows = [{'url': f'https://x.com/{i}', 'language': lang, 'warc_date': '2026-02-24T00:00:00Z',
             'content_type': 'text/html', 'record_id': f'r{i}', 'html': html}
            for i, (lang, html) in enumerate([('en', ARTICLE), ('zh', ARTICLE), ('en', b'')])]
    pq.write_table(pa.Table.from_pylist(rows, ArticleHtmlArchiver.SCHEMA), tmp_path / 'h.parquet')
    counts = EntityExtractor(rule_based_nlp()).write(str(tmp_path / 'h.parquet'), str(tmp_path / 'n.parquet'))
    table = pq.read_table(tmp_path / 'n.parquet')
    en, zh, empty = table.to_pylist()
    assert counts == {'pages': 3, 'ner_pages': 1, 'entities': len(en['entities'])}
    assert [r['record_id'] for r in (en, zh, empty)] == ['r0', 'r1', 'r2']
    assert {e['text'] for e in en['entities']} == {'Anthropic', 'DeepSeek'}
    assert all(en['text'][e['start_char']:e['end_char']] == e['text'] for e in en['entities'])
    assert zh['entities'] is None and zh['ner_chars'] == 0 and zh['text']  # not English: text kept, no NER
    assert empty['entities'] is None
    assert table.schema.metadata[b'model'] == b'en_rules-0.0'
