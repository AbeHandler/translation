"""
A demo of the dispersion engine (PhraseCrossingDetector) on built-in examples, both directions, no data files:
    en -> zh   Anthropic's statement on the Department of War, and two Chinese renderings of it
    zh -> en   a line from the CAC's generative AI measures, and an English rendering of it
For each focal span (phrases, and one whole sentence): its uptake in each target (verbatim, translated,
paraphrased, dropped), why, and its rendering (pieces joined with …); then per focal span its selection (shares of
each uptake) and dispersion (distinct renderings, entropy). Downloads LaBSE and mBERT once (~2 GB).

Run from the repo root:
    python -m src.dispersion.demo
"""
from collections import defaultdict

from src.dispersion.aligners.simalign import SimAlignAligner
from src.dispersion.crossing import PhraseCrossingDetector
from src.dispersion.dispersion import dispersion, selection
from src.dispersion.encoders import labse
from src.dispersion.sentences import SentenceMatcher
from src.dispersion.types import Doc, Focal

EN_SOURCE = Doc('anthropic-statement', 'en', (
    "We have held to two exceptions. First, we do not believe that today's frontier AI models are reliable enough "
    "to be used in fully autonomous weapons. Second, we believe that mass domestic surveillance of Americans "
    "constitutes a violation of fundamental rights. These questions of AI governance matter to everyone. "
    "Claude has been used across classified networks."))
ZH_TARGETS = [
    Doc('huxiu', 'zh', ("Anthropic坚持两项例外。第一，我们不认为当今的前沿人工智能模型足够可靠，可以用于完全自主的武器。"
                        "第二，我们认为对美国人进行大规模国内监控侵犯了基本权利。这些人工智能治理问题关系到每个人。"
                        "Claude已被用于各个机密网络。")),
    Doc('thepaper', 'zh', ("Anthropic表示，第一，如今的尖端AI模型还不够可靠，不能用于全自主武器。"
                           "第二，大规模监控美国民众侵犯基本权利。五角大楼对此十分不满。")),
]
FIRST = ("First, we do not believe that today's frontier AI models are reliable enough to be used in fully "
         "autonomous weapons.")
EN_FOCALS = [Focal(t, 'en') for t in ['frontier AI models', 'autonomous weapons', 'mass domestic surveillance',
                                      'governance', 'Claude', 'classified networks']]
EN_FOCALS.append(Focal(FIRST, 'en', span=(EN_SOURCE.text.index(FIRST), EN_SOURCE.text.index(FIRST) + len(FIRST))))

ZH_SOURCE = Doc('cac-measures', 'zh', ("坚持发展和安全并重、促进创新和依法治理相结合的原则。"
                                       "提供者应当依法开展预训练、优化训练等训练数据处理活动。"))
EN_TARGETS = [Doc('reuters', 'en', ("The rules uphold the principle of giving equal weight to development and security "
                                    "and of combining innovation with governance according to law. Providers shall "
                                    "carry out training data processing activities such as pre-training in accordance "
                                    "with the law."))]
ZH_FOCALS = [Focal(t, 'zh') for t in ['安全', '治理', '训练数据']]
KNOWN = {'agents': ['智能体'], 'compute': ['算力']}   # renderings LaBSE scores low


def label(focal):
    return focal.text if len(focal.text) <= 28 else focal.text[:25] + '...'


def run(source, targets, focals, detector):
    by_focal = defaultdict(list)
    for target in targets:
        print(f'\n{source.id} ({source.lang}) -> {target.id} ({target.lang})')
        for focal in focals:
            for p in detector.detect(focal, source, target):
                by_focal[label(focal)].append(p)
                print(f'  {label(focal):28} {p.uptake:11} {p.target_text[:24] or "-":24} '
                      f'({p.reason}; span {p.span_score:.2f}, sentence {p.sentence_score:.2f})')
    print('\nselection and dispersion:')
    for text, preds in by_focal.items():
        shares = ', '.join(f'{u} {v:.0%}' for u, v in selection(preds).items() if v)
        d = dispersion(preds)
        print(f'  {text:28} {shares:38} {d["distinct"]} distinct: {dict(d["renderings"])}')


def main():
    encode = labse()
    matcher = SentenceMatcher(encode, min_score=0.6)   # a sentence below 0.6 has no counterpart
    run(EN_SOURCE, ZH_TARGETS, EN_FOCALS,
        PhraseCrossingDetector(matcher, SimAlignAligner('en', 'zh'), encode, known=KNOWN))
    run(ZH_SOURCE, EN_TARGETS, ZH_FOCALS, PhraseCrossingDetector(matcher, SimAlignAligner('zh', 'en'), encode))


if __name__ == '__main__':
    main()
