"""
Direct quotes of every page in a NER file (src/ner_html.py), for the CC-NEWS pipeline's quotes step. The
quotes are found in the NER file's text, so their offsets line up with the entities': a quote can be joined to
the entities in or near it.

For every NER file, writes one quotes file with a row per quotation (pages without quotes have no rows):
    record_id, url                                  the page, to join on
    quote, quote_type, quote_start, quote_end       quote_type: LeftSpeaker, RightSpeaker or Unknown
    speaker, speaker_start, speaker_end             null when there is none (Unknown, or none found)
    n_words                                         the quote's length, to drop short fragments later
The model directory is in the file's metadata. Only English pages are read (DirectQuote is English).
"""
import logging
import os
import time

import pyarrow as pa
import pyarrow.parquet as pq

logger = logging.getLogger(__name__)

SCHEMA = pa.schema([
    ('record_id', pa.string()), ('url', pa.string()),
    ('quote', pa.string()), ('quote_type', pa.string()), ('quote_start', pa.int32()), ('quote_end', pa.int32()),
    ('speaker', pa.string()), ('speaker_start', pa.int32()), ('speaker_end', pa.int32()),
    ('n_words', pa.int32()),
])
LANGUAGES = ('en',)
READ_ROWS = 200


class QuoteFileWriter:
    def __init__(self, extractor, model_dir):
        self.extractor = extractor  # a QuoteExtractor
        self.model_dir = str(model_dir)

    def write(self, ner_path, out_path):
        """Write out_path (via .part, so a partial file never looks done). Returns counts."""
        counts = {'pages': 0, 'pages_with_quotes': 0, 'quotes': 0}
        schema = SCHEMA.with_metadata({'model_dir': self.model_dir})
        started = time.time()
        with pq.ParquetWriter(out_path + '.part', schema, compression='zstd') as writer:
            parquet = pq.ParquetFile(ner_path)
            total = parquet.metadata.num_rows
            for batch in parquet.iter_batches(batch_size=READ_ROWS, columns=['record_id', 'url', 'language', 'text']):
                rows = []
                for page in batch.to_pylist():
                    counts['pages'] += 1
                    page_rows = self.rows(page)
                    counts['pages_with_quotes'] += bool(page_rows)
                    rows += page_rows
                if rows:
                    writer.write_table(pa.Table.from_pylist(rows, schema))
                counts['quotes'] += len(rows)
                elapsed = time.time() - started
                logger.info('%s: %d/%d pages, %d quotes (%.1f pages/s)', os.path.basename(ner_path),
                            counts['pages'], total, counts['quotes'], counts['pages'] / elapsed)
        os.rename(out_path + '.part', out_path)
        return counts

    def rows(self, page):
        if page['language'] not in LANGUAGES or not page['text']:
            return []
        return [{'record_id': page['record_id'], 'url': page['url'], **quote,
                 'n_words': len(quote['quote'].split())}
                for quote in self.extractor.predict(page['text'])]
