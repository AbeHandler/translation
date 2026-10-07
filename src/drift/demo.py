"""
A demo of the drift scorers on two quotes from one Chinese article (Jiemian, "“DeepSeek风暴”，让微软们疯狂撒钱？",
https://www.jiemian.com/article/12349458.html), each attributed to its speaker inside quotation marks:
    Sundar Pichai   rendered faithfully
    Satya Nadella   "a commodity we just can't get enough of" (appetite) rendered as 一种永远无法满足的商品,
                    "a commodity that can never be satisfied" (demand that is never met): a shift in meaning
plus a faithful rendering of Nadella's phrase for comparison. Downloads LaBSE and an NLI model (~1 GB) once. -llm
adds the LLM rater (gpt-6-luna, OPENAI_API_KEY from .env; paid: three calls, a fraction of a cent).

Run from the repo root:
    python -m src.drift.demo
    python -m src.drift.demo -llm
"""
import sys

from src.dispersion.encoders import labse
from src.drift.quotes import is_quoted
from src.drift.llm import LLMDrift
from src.drift.scorers import EmbeddingDrift, NLIDrift

ARTICLE = ('谷歌CEOSundar Pichai反复强调，对谷歌而言，“在AI领域投资不足的风险远远大于过度投资的风险。” '
           '「AI将成为一种永远无法满足的商品」。Nadella这样写道。')
CASES = [
    ('Pichai, as quoted',
     'The risk of under-investing in AI is dramatically greater than the risk of over-investing.',
     '在AI领域投资不足的风险远远大于过度投资的风险。'),
    ('Nadella, as quoted',
     "As AI gets more efficient and accessible, we will see its use skyrocket, turning it into a commodity we just "
     "can't get enough of.",
     'AI将成为一种永远无法满足的商品'),
    ('Nadella, a faithful rendering',
     "As AI gets more efficient and accessible, we will see its use skyrocket, turning it into a commodity we just "
     "can't get enough of.",
     '随着AI变得更高效、更普及，它的使用量将激增，成为一种我们永远都不嫌多的商品。'),
]


def main():
    scorers = [EmbeddingDrift(labse()), NLIDrift()]
    if '-llm' in sys.argv:
        from dotenv import load_dotenv
        from config.paths import ENV_PATH
        load_dotenv(ENV_PATH)
        scorers.append(LLMDrift())
    for name, source, rendering in CASES:
        start = ARTICLE.find(rendering.rstrip('。'))
        quoted = start >= 0 and is_quoted((start, start + len(rendering.rstrip('。'))), ARTICLE)
        print(f'\n{name}{" (inside quotation marks in the article)" if quoted else ""}')
        print(f'  EN: {source}\n  ZH: {rendering}')
        for scorer in scorers:
            d = scorer.score(source, rendering)
            print(f'  {scorer.name:9} size {d.size:.2f}  {d.kind or "":12} {d.details}')


if __name__ == '__main__':
    main()
