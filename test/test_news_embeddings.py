"""Run from the repo root: python -m pytest test/"""
import json

import numpy as np
import pyarrow as pa
import pyarrow.parquet as pq

from src.cc_news import ArticleHtmlArchiver
from src.news_embeddings import NewsEmbedder

PARA = '<p>{}</p>'
AI = 'The government released new rules for generative AI services on Thursday, the regulator said in a statement.'
CHIPS = 'TSMC engineers allegedly shared photos of the 2nm process with a Japanese firm, prosecutors said on Friday.'


class FakeEncoder:
    def encode(self, texts):
        return np.ones((len(texts), 4), dtype=np.float32) / 2


def page(i, language, sentence, menu=''):
    html = f'<html><body><nav>{menu}</nav><article>{PARA.format(sentence) * 8}</article></body></html>'
    return {'url': f'https://n.com/{i}', 'language': language, 'warc_date': '2023-07-14T00:00:00Z',
            'content_type': 'text/html', 'record_id': f'<urn:{i}>', 'html': html.encode()}


def test_only_english_articles_whose_body_says_ai(tmp_path):
    pages = [page(0, 'en', AI), page(1, 'en', CHIPS, menu='AI | Gaming'), page(2, 'zh', AI), page(3, 'en', AI)]
    pq.write_table(pa.Table.from_pylist(pages, ArticleHtmlArchiver.SCHEMA), tmp_path / 'W.parquet')
    links = [{'url': p['url'], 'record_id': p['record_id'], 'language': p['language'], 'ai_mentions': 8, 'links': []}
             for p in pages[:3]] + [{'url': pages[3]['url'], 'record_id': pages[3]['record_id'], 'language': 'en',
                                     'ai_mentions': 0, 'links': []}]  # the links file says no AI: not parsed
    (tmp_path / 'W.jsonl').write_text(''.join(json.dumps(r) + '\n' for r in links))
    embedder = NewsEmbedder(FakeEncoder(), str(tmp_path))
    assert embedder.embed_file(str(tmp_path / 'W.parquet'), str(tmp_path / 'out.parquet')) == {'articles': 1}
    rows = pq.read_table(tmp_path / 'out.parquet').to_pylist()
    assert rows[0]['url'] == 'https://n.com/0' and rows[0]['body_ai_mentions'] == 8 and len(rows[0]['embedding']) == 4
