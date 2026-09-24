"""
Sentence embeddings of the article in each page of an HTML Parquet file (the CC-NEWS format of
ArticleHtmlArchiver in src/cc_news.py, which the scrapy crawls also write). Logic only: no paths.

For every HTML file, writes one embeddings file with a row per page, in the same order:
    record_id, url, language   copied from the HTML file, to join on
    text_chars                 length of the text that was embedded (0: no text found, embedding null)
    embedding                  normalized float32 vector
The text is newspaper4k's title + article body. The model reads at most its max length in tokens (512 for
bge-base), so long articles are embedded from their start. The model name is in the file's metadata.

embed_all() is the worker loop: many copies can run at once (e.g. as SLURM jobs). Each takes the HTML files
that have no embeddings file yet, in random order, and claims each with a .lock next to its output.
"""
import logging
import os
import random

import pyarrow as pa
import pyarrow.parquet as pq
from newspaper import Article

from src.cc_news import claim_lock

logger = logging.getLogger(__name__)

SCHEMA = pa.schema([
    ('record_id', pa.string()),
    ('url', pa.string()),
    ('language', pa.string()),
    ('text_chars', pa.int32()),
    ('embedding', pa.list_(pa.float32())),
])


def article_text(html, url, language):
    """newspaper4k's title and body text, or '' if it finds none."""
    # fetch_images=False: otherwise parse() downloads the page's images, which is most of its time
    article = Article(url, language=language or 'zh', fetch_images=False)
    article.download(input_html=html.decode('utf-8', errors='replace'))
    article.parse()
    return f'{article.title}\n{article.text}'.strip()


class HtmlEmbedder:
    def __init__(self, model, model_name, batch_size=32):
        self.model = model  # a SentenceTransformer
        self.model_name = model_name
        self.batch_size = batch_size

    def embed_file(self, html_path, out_path):
        """Write out_path (via .part, so a partial file never looks done). Returns counts."""
        pages = pq.read_table(html_path, columns=['record_id', 'url', 'language', 'html']).to_pylist()
        texts = [self.text_of(page) for page in pages]
        has_text = [i for i, text in enumerate(texts) if text]
        vectors = self.model.encode([texts[i] for i in has_text], batch_size=self.batch_size,
                                    normalize_embeddings=True, convert_to_numpy=True)
        embeddings = [None] * len(pages)
        for i, vector in zip(has_text, vectors):
            embeddings[i] = vector.tolist()
        rows = [{'record_id': page['record_id'], 'url': page['url'], 'language': page['language'],
                 'text_chars': len(text), 'embedding': embedding}
                for page, text, embedding in zip(pages, texts, embeddings)]
        schema = SCHEMA.with_metadata({'model': self.model_name})
        pq.write_table(pa.Table.from_pylist(rows, schema), out_path + '.part', compression='zstd')
        os.rename(out_path + '.part', out_path)
        return {'pages': len(pages), 'embedded': len(has_text)}

    def text_of(self, page):
        try:
            return article_text(page['html'], page['url'], page['language'])
        except Exception as exc:  # garbled pages; the row keeps text_chars 0 and no embedding
            logger.debug('no text for %s: %s', page['url'], exc)
            return ''


def embed_all(html_paths, out_path_of, embedder, max_files=None):
    """Embed every HTML file whose output (out_path_of(html_path)) doesn't exist yet and that no other
    worker has claimed. Returns the number of files this worker embedded."""
    todo = [path for path in html_paths if not os.path.exists(out_path_of(path))]
    random.shuffle(todo)
    logger.info('%d HTML files, %d without embeddings', len(html_paths), len(todo))
    n_done = 0
    for html_path in todo:
        out_path = out_path_of(html_path)
        os.makedirs(os.path.dirname(out_path), exist_ok=True)
        if os.path.exists(out_path) or not claim_lock(out_path + '.lock'):
            continue
        try:
            info = embedder.embed_file(html_path, out_path)
        finally:
            os.remove(out_path + '.lock')  # also on failure, so a rerun can pick the file up
        logger.info('embedded %s %s', html_path, info)
        n_done += 1
        if max_files and n_done >= max_files:
            break
    return n_done
