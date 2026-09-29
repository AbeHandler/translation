"""Run from the repo root: python -m pytest test/"""
import os

from src.common_crawl_full.filter import is_english_ai_page
from src.common_crawl_full.worker import out_path, process_warcs

EN = ('<html><body><p>' + 'The new AI model from the lab was released to researchers this week. ' * 10
      + '</p></body></html>')


def test_english_pages_saying_ai_are_kept():
    assert is_english_ai_page(EN.encode())[0]
    assert not is_english_ai_page(EN.replace('AI', 'software').encode())[0]
    assert not is_english_ai_page(b'<html><script>var AI = 1;</script><body>' + b'Hello there. ' * 20 + b'</body>')[0]
    assert not is_english_ai_page(('<html><body>' + '新的AI模型本周向研究人员发布了。' * 10 + '</body></html>').encode())[0]


def test_worker_does_each_warc_once_and_survives_a_failure(tmp_path):
    paths = [f'crawl-data/C/segments/s/warc/CC-MAIN-{i}.warc.gz' for i in range(4)]
    (tmp_path / 'list.txt').write_text('\n'.join(paths) + '\n')
    done = []

    def process(path, out):
        if path.endswith('-2.warc.gz') and path not in done:
            done.append(path)
            raise ConnectionError('throttled')
        done.append(path)
        open(out, 'w').close()
        return {}
    assert out_path(str(tmp_path), paths[0]).endswith('CC-MAIN-0.ai.warc.gz')
    assert process_warcs(str(tmp_path / 'list.txt'), str(tmp_path), process, seed=1) == 3
    assert process_warcs(str(tmp_path / 'list.txt'), str(tmp_path), process, seed=2) == 1  # the failed one, retried
    assert sorted(f for f in os.listdir(tmp_path) if f.endswith('.ai.warc.gz')) == [
        f'CC-MAIN-{i}.ai.warc.gz' for i in range(4)]
    assert not [f for f in os.listdir(tmp_path) if f.endswith('.lock')]
