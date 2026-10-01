"""
News-similarity embeddings (src/news_similarity.py) of the English CC-NEWS articles about AI, for finding story
clusters and media storms. Logic only: no paths.

One output file per cc_html file (WARC), same name, a row per English article whose body says "AI":
    url, record_id, warc_date   to join on (cc_html, cc_links) and to place the article in time
    title, lead                 the headline and the first LEAD_CHARS of the body, for reading clusters
    text_chars                  length of headline + body
    body_ai_mentions            "AI" in the article body (readability; src/ai_mentions.py)
    embedding                   unit-length vector, float16 (cosine = dot product)
Which articles: those the links file (cc_links/<warc>.jsonl) records as English with "AI" somewhere on the page
(ai_mentions) are parsed, and kept when "AI" is in the body itself (min_body_ai), so a hardware story with an
AI menu item drops out. Links files older than ai_mentions: every English page is parsed.
"""
import json
import logging
import os

import pyarrow as pa
import pyarrow.parquet as pq

from src.ai_mentions import mentions_ai
from src.cc_news import readable_article

logger = logging.getLogger(__name__)
LEAD_CHARS = 500
SCHEMA = pa.schema([
    ('url', pa.string()),
    ('record_id', pa.string()),
    ('warc_date', pa.string()),
    ('title', pa.string()),
    ('lead', pa.string()),
    ('text_chars', pa.int32()),
    ('body_ai_mentions', pa.int32()),
    ('embedding', pa.list_(pa.float16())),
])


def ai_candidates(links_path):
    """record_ids of the English pages the links file says mention "AI"; None if it doesn't record that."""
    ids = set()
    with open(links_path, encoding='utf-8') as f:
        for line in f:
            row = json.loads(line)
            if 'ai_mentions' not in row:
                return None
            if row.get('language') == 'en' and row['ai_mentions'] >= 1:
                ids.add(row['record_id'])
    return ids


class NewsEmbedder:
    def __init__(self, encoder, links_dir, min_body_ai=1):
        self.encoder = encoder  # a NewsSimilarityEncoder
        self.links_dir = links_dir
        self.min_body_ai = min_body_ai

    def links_path(self, html_path):
        return os.path.join(self.links_dir, os.path.basename(html_path).removesuffix('.parquet') + '.jsonl')

    def articles(self, html_path):
        """{url, record_id, warc_date, title, body} of the file's English articles whose body says "AI"."""
        links_path = self.links_path(html_path)
        wanted = ai_candidates(links_path) if os.path.exists(links_path) else None
        parquet = pq.ParquetFile(html_path)
        columns = ['url', 'record_id', 'warc_date', 'language', 'html']
        for batch in parquet.iter_batches(batch_size=200, columns=columns):
            for page in batch.to_pylist():
                if page['language'] != 'en' or (wanted is not None and page['record_id'] not in wanted):
                    continue
                try:
                    title, body = readable_article(page['html'])
                    body = ' '.join(body.text_content().split())
                except Exception as exc:  # garbled pages
                    logger.debug('no article in %s: %s', page['url'], exc)
                    continue
                if mentions_ai(body) >= self.min_body_ai:
                    yield {**{k: page[k] for k in ('url', 'record_id', 'warc_date')}, 'title': title, 'body': body}

    def embed_file(self, html_path, out_path):
        """Write out_path (via .part, so a partial file never looks done). Returns counts."""
        articles = list(self.articles(html_path))
        vectors = self.encoder.encode([f"{a['title']}\n{a['body']}" for a in articles])
        rows = [{'url': a['url'], 'record_id': a['record_id'], 'warc_date': a['warc_date'], 'title': a['title'],
                 'lead': a['body'][:LEAD_CHARS], 'text_chars': len(a['title']) + len(a['body']) + 1,
                 'body_ai_mentions': mentions_ai(a['body']), 'embedding': vector.astype('float16').tolist()}
                for a, vector in zip(articles, vectors)]
        pq.write_table(pa.Table.from_pylist(rows, SCHEMA), out_path + '.part', compression='zstd')
        os.rename(out_path + '.part', out_path)
        return {'articles': len(rows)}
