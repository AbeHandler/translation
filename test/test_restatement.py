"""Run from the repo root: python -m pytest test/"""
import numpy as np

from src.restatement.align import Aligner, label
from src.restatement.pages import anchor_sentence, chinese_sentences, citing_paragraphs, same_url

EN_PAGE = ('<html><body><nav><a href="https://www.163.com/dy/article/K.html">menu</a></nav><article>'
           '<p>Tencent built CodeBuddy. The company <a href="https://163.com/dy/article/K.html/">reported</a> that '
           'half of new code was written with AI. Others disagree.</p></article></body></html>')


def test_citing_paragraph_and_anchor_sentence_skip_navigation():
    (found,) = citing_paragraphs(EN_PAGE, 'https://example.com/a', 'https://www.163.com/dy/article/K.html')
    assert found['anchor_text'] == 'reported' and found['paragraph'].startswith('Tencent built CodeBuddy.')
    assert anchor_sentence(found['paragraph'], 'reported') == ('The company reported that half of new code was '
                                                               'written with AI.')
    assert same_url('http://www.x.com/a/', 'https://x.com/a#top')


def test_chinese_sentences_drop_menu_fragments():
    text = '首页 新闻 科技。超过90%的腾讯工程师使用AI编程助手辅助编程。50%的新增代码由AI辅助生成！'
    assert chinese_sentences(text) == ['超过90%的腾讯工程师使用AI编程助手辅助编程。', '50%的新增代码由AI辅助生成！']


def test_alignment_labels_from_the_best_score():
    class FakeModel:
        def encode(self, sentences, **kwargs):  # one-hot per distinct meaning: 'same' texts get the same vector
            return np.array([[1.0, 0.0] if 'same' in s else [0.0, 1.0] for s in sentences])
    rows, best = Aligner(FakeModel()).align(['same en', 'other en'], ['same zh', 'x zh'])
    assert best == 1.0 and rows[0]['matches'][0]['zh'] == 'same zh' and label(best) == 'translation'
    assert label(0.7) == 'paraphrase' and label(0.3) == 'neither' and Aligner(FakeModel()).align([], ['a']) == ([], 0.0)
