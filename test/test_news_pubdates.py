"""Run from the repo root: python -m pytest test/"""
import pyarrow as pa
import pyarrow.parquet as pq

from src.cc_news import ArticleHtmlArchiver
from src.news_pubdates import date_file

DATED = ('<html><head><meta property="article:published_time" content="2023-07-13T09:00:00+08:00"></head>'
         '<body><p>China published rules for generative AI.</p></body></html>')
UNDATED = '<html><body><p>Nothing here says when.</p></body></html>'


def test_pubdate_from_the_page_else_the_crawl_date(tmp_path):
    rows = [{'url': f'https://n.com/{i}', 'language': 'en', 'warc_date': '2023-07-20T00:00:00Z',
             'content_type': 'text/html', 'record_id': str(i), 'html': html.encode()}
            for i, html in enumerate([DATED, UNDATED, UNDATED])]
    (tmp_path / 'html').mkdir()
    pq.write_table(pa.Table.from_pylist(rows, ArticleHtmlArchiver.SCHEMA), tmp_path / 'html' / 'W.parquet')
    pq.write_table(pa.table({'url': ['https://n.com/0', 'https://n.com/1']}), tmp_path / 'W.parquet')  # embedded
    counts = date_file(str(tmp_path / 'W.parquet'), str(tmp_path / 'html'), str(tmp_path / 'out.parquet'))
    assert counts == {'articles': 2, 'with_pubdate': 1}
    out = {r['url']: r for r in pq.read_table(tmp_path / 'out.parquet').to_pylist()}
    assert out['https://n.com/0']['date'] == '2023-07-13' and out['https://n.com/0']['gap_days'] == 7
    assert out['https://n.com/1']['date'] == '2023-07-20' and out['https://n.com/1']['pubdate'] is None
