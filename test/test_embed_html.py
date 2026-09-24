"""Run from the repo root: python -m pytest test/"""
import numpy as np
import pyarrow as pa
import pyarrow.parquet as pq

from src.cc_news import ArticleHtmlArchiver
from src.embed_html import HtmlEmbedder, embed_all

ARTICLE = ('<html><head><title>标题</title></head><body><article>'
           + '<p>这是一篇关于大模型安全的文章，介绍了新的开源工具和评测基准。</p>' * 5
           + '</article></body></html>').encode('utf-8')


class FakeModel:
    """Stands in for a SentenceTransformer: one unit vector per text."""

    def encode(self, texts, **kwargs):
        return np.ones((len(texts), 4), dtype=np.float32) / 2


def write_html_file(path, htmls):
    rows = [{'url': f'https://example.com/p/{i}.html', 'language': 'zh', 'warc_date': '2026-09-24T00:00:00Z',
             'content_type': 'text/html', 'record_id': f'<urn:uuid:{i}>', 'html': html}
            for i, html in enumerate(htmls)]
    pq.write_table(pa.Table.from_pylist(rows, ArticleHtmlArchiver.SCHEMA), path)


def test_one_row_per_page_in_order_and_null_embedding_without_text(tmp_path):
    html_path = str(tmp_path / 'part.parquet')
    write_html_file(html_path, [ARTICLE, b'', ARTICLE])
    out_path = str(tmp_path / 'emb.parquet')
    info = HtmlEmbedder(FakeModel(), 'fake-model').embed_file(html_path, out_path)
    table = pq.read_table(out_path)
    assert info == {'pages': 3, 'embedded': 2}
    assert table['record_id'].to_pylist() == ['<urn:uuid:0>', '<urn:uuid:1>', '<urn:uuid:2>']
    assert table['embedding'][1].as_py() is None and table['text_chars'][1].as_py() == 0
    assert len(table['embedding'][0].as_py()) == 4
    assert table.schema.metadata[b'model'] == b'fake-model'


def test_embed_all_skips_files_already_embedded(tmp_path):
    html_path = str(tmp_path / 'part.parquet')
    write_html_file(html_path, [ARTICLE])
    embedder = HtmlEmbedder(FakeModel(), 'fake-model')
    out_path_of = lambda path: path.replace('part', 'emb')  # noqa: E731
    assert embed_all([html_path], out_path_of, embedder) == 1
    assert embed_all([html_path], out_path_of, embedder) == 0
