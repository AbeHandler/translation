"""
Named entities of every page in an HTML Parquet file (the CC-NEWS format of ArticleHtmlArchiver in
src/cc_news.py), for filtering pages later, e.g. by a gazetteer. Logic only: no paths.

For every HTML file, writes one NER file with a row per page, in the same order:
    record_id, url, language   copied from the HTML file, to join on
    text                       newspaper4k's title + article body (src/embed_html.py article_text), which the
                               entity offsets refer to
    ner_chars                  how much of text went through NER (MAX_CHARS at most; 0: not run)
    entities                   [{text, label, start_char, end_char}], or null when NER was not run: the page
                               isn't English (the model is en_core_web_trf) or has no text
The spaCy model's name and version are in the file's metadata. Find pages naming a gazetteer entry with e.g.
duckdb:  SELECT url, e.text FROM 'cc_ner/*.parquet', UNNEST(entities) AS t(e) WHERE e.label = 'ORG' AND ...
"""
import logging
import os

import pyarrow as pa
import pyarrow.parquet as pq

from src.embed_html import article_text

logger = logging.getLogger(__name__)

ENTITY = pa.struct([('text', pa.string()), ('label', pa.string()), ('start_char', pa.int32()),
                    ('end_char', pa.int32())])
SCHEMA = pa.schema([
    ('record_id', pa.string()),
    ('url', pa.string()),
    ('language', pa.string()),
    ('text', pa.string()),
    ('ner_chars', pa.int32()),
    ('entities', pa.list_(ENTITY)),
])
NER_LANGUAGES = ('en',)
MAX_CHARS = 20_000  # the transformer's cost grows with length; news articles are almost always shorter
READ_ROWS = 200     # pages read (and written) at a time, so a whole file never sits in memory
# en_core_web_trf also tags, parses and lemmatizes; only the transformer and NER are needed
NOT_NEEDED = ('tagger', 'parser', 'attribute_ruler', 'lemmatizer')


def load_ner_model(name='en_core_web_trf'):
    import spacy  # here, so importing this module doesn't need spaCy
    return spacy.load(name, exclude=list(NOT_NEEDED))


class EntityExtractor:
    def __init__(self, nlp, batch_size=16):
        self.nlp = nlp  # a spaCy pipeline with ner
        self.batch_size = batch_size
        self.model = f'{nlp.meta["lang"]}_{nlp.meta["name"]}-{nlp.meta["version"]}'

    def write(self, html_path, out_path):
        """Write out_path (via .part, so a partial file never looks done). Returns counts."""
        counts = {'pages': 0, 'ner_pages': 0, 'entities': 0}
        schema = SCHEMA.with_metadata({'model': self.model})
        with pq.ParquetWriter(out_path + '.part', schema, compression='zstd') as writer:
            parquet = pq.ParquetFile(html_path)
            for batch in parquet.iter_batches(batch_size=READ_ROWS, columns=['record_id', 'url', 'language', 'html']):
                rows = self.rows(batch.to_pylist())
                writer.write_table(pa.Table.from_pylist(rows, schema))
                counts['pages'] += len(rows)
                counts['ner_pages'] += sum(row['entities'] is not None for row in rows)
                counts['entities'] += sum(len(row['entities'] or []) for row in rows)
        os.rename(out_path + '.part', out_path)
        return counts

    def rows(self, pages):
        texts = [self.text_of(page) for page in pages]
        todo = [i for i, (page, text) in enumerate(zip(pages, texts)) if text and page['language'] in NER_LANGUAGES]
        entities = [None] * len(pages)
        docs = self.nlp.pipe((texts[i][:MAX_CHARS] for i in todo), batch_size=self.batch_size)
        for i, doc in zip(todo, docs):
            entities[i] = [{'text': ent.text, 'label': ent.label_, 'start_char': ent.start_char,
                            'end_char': ent.end_char} for ent in doc.ents]
        return [{'record_id': page['record_id'], 'url': page['url'], 'language': page['language'], 'text': text,
                 'ner_chars': min(len(text), MAX_CHARS) if entities[i] is not None else 0, 'entities': entities[i]}
                for i, (page, text) in enumerate(zip(pages, texts))]

    def text_of(self, page):
        try:
            return article_text(page['html'], page['url'], page['language'])
        except Exception as exc:  # garbled pages; the row keeps no text and no entities
            logger.debug('no text for %s: %s', page['url'], exc)
            return ''
