"""
A demo of the dispersion engine on built-in examples, both directions, no data files needed:
    en -> zh   Anthropic's statement on the Department of War, and two Chinese renderings of it
    zh -> en   a line from the CAC's generative AI measures, and an English rendering of it
For each focal phrase: the sentence it was matched to, its rendering (pieces joined with …), and its status; then
the dispersion of each phrase over the targets. Downloads LaBSE and mBERT once (~2 GB).

Run from the repo root:
    python -m src.dispersion.demo
"""
from collections import defaultdict

from src.dispersion.align import align
from src.dispersion.aligners.simalign import SimAlignAligner
from src.dispersion.dispersion import dispersion
from src.dispersion.encoders import labse
from src.dispersion.sentences import SentenceMatcher
from src.dispersion.types import Doc, Focal

EN_SOURCE = Doc('anthropic-statement', 'en', (
    "We have held to two exceptions. First, we do not believe that today's frontier AI models are reliable enough "
    "to be used in fully autonomous weapons. Second, we believe that mass domestic surveillance of Americans "
    "constitutes a violation of fundamental rights. These questions of AI governance matter to everyone."))
ZH_TARGETS = [
    Doc('huxiu', 'zh', ("Anthropic坚持两项例外。第一，我们不认为当今的前沿人工智能模型足够可靠，可以用于完全自主的武器。"
                        "第二，我们认为对美国人进行大规模国内监控侵犯了基本权利。这些人工智能治理问题关系到每个人。")),
    Doc('thepaper', 'zh', ("Anthropic表示，第一，如今的尖端AI模型还不够可靠，不能用于全自主武器。"
                           "第二，大规模监控美国民众侵犯基本权利。五角大楼对此十分不满。")),
]
EN_FOCALS = ['frontier AI models', 'autonomous weapons', 'mass domestic surveillance', 'governance']

ZH_SOURCE = Doc('cac-measures', 'zh', ("坚持发展和安全并重、促进创新和依法治理相结合的原则。"
                                       "提供者应当依法开展预训练、优化训练等训练数据处理活动。"))
EN_TARGETS = [Doc('reuters', 'en', ("The rules uphold the principle of giving equal weight to development and security "
                                    "and of combining innovation with governance according to law. Providers shall "
                                    "carry out training data processing activities such as pre-training in accordance "
                                    "with the law."))]
ZH_FOCALS = ['安全', '治理', '训练数据']


def run(source, targets, focals, matcher, aligner):
    by_focal = defaultdict(list)
    for target in targets:
        print(f'\n{source.id} ({source.lang}) -> {target.id} ({target.lang})')
        for text in focals:
            for p in align(Focal(text, source.lang), source, target, matcher, aligner):
                by_focal[text].append(p)
                where = f'sentence {p.sentence_score:.2f}' if p.target_sentence else 'no matching sentence'
                print(f'  {text:28} {p.status:9} {p.target_text or "-":16} ({where})')
    print('\ndispersion:')
    for text, preds in by_focal.items():
        d = dispersion(preds)
        print(f'  {text:28} {d["distinct"]} distinct, entropy {d["entropy"]:.2f}: {dict(d["renderings"])}')


def main():
    matcher = SentenceMatcher(labse(), min_score=0.75)   # below 0.75 sentence pairs are rarely translations
    run(EN_SOURCE, ZH_TARGETS, EN_FOCALS, matcher, SimAlignAligner('en', 'zh'))
    run(ZH_SOURCE, EN_TARGETS, ZH_FOCALS, matcher, SimAlignAligner('zh', 'en'))


if __name__ == '__main__':
    main()
