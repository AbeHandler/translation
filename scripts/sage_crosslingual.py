#!/usr/bin/env python
"""
How a covariate's vocabulary differs between English and Chinese coverage, on one shared vocabulary: is "AI bubble"
more Nvidia-like in English than in Chinese? English and Chinese documents (a fightin sample's docs.parquet) are
counted over concepts (src/sage/crosslingual.py: Chinese phrases mapped to their nearest English phrase by LaBSE,
names and slogans by the known renderings), then one SAGE (src/sage) is fitted with facets
    lang, covariate, lang x covariate (and -outlet: outlet, absorbing house style and boilerplate)
For each concept and language, D = how much more the covariate's documents use it (log scale), from the components:
    D_lang = (eta_cov[yes] - eta_cov[no]) + (eta_lang.cov[lang.yes] - eta_lang.cov[lang.no])
    gap = D_zh - D_en: > 0 more tied to the covariate in Chinese coverage, < 0 more in English
The interaction carries the gap, with SAGE's sparsity prior: a concept without real evidence of a difference has a
gap of exactly 0. Output in results/sage_crosslingual/<experiment>/:
    compare.tsv     concept, its Chinese forms, uses per language and covariate value, D_en, D_zh, gap
    shared.tsv      the concepts used in both languages (-min-uses each): where the comparison means something
    mapping.tsv     Chinese unit -> concept, cosine (cached: the embedding is the slow part)

Run as a module from the repo root:
    python -m scripts.sage_crosslingual -docs /tmp/fightin/all_5k/docs.parquet \\
        -covariate nvidia='Nvidia|英伟达' -exclude 'jensen|huang|黄仁勋' -experiment-name nvidia
"""
import argparse
import hashlib
import os
import re

import numpy as np
import pandas as pd

from config.paths import FIGHTIN_RENDERINGS_PATH, REPO_ROOT, STOPWORDS_EN_PATH
from src.fightin.concepts import EMBED_VERSION, read_stopwords
from src.fightin.renderings import KnownRenderings
from src.fightin.units import parse_ns
from src.sage.crosslingual import concept_map, to_concepts
from src.sage.featurise import count_matrix, doc_units, vocabulary
from src.sage.models import AdditiveSAGE, sparsity

NAME = 'sage_crosslingual'


def parse_args():
    parser = argparse.ArgumentParser(description="A covariate's vocabulary in English vs Chinese, joint SAGE")
    parser.add_argument('-docs', required=True, help='a parquet of documents in both languages')
    parser.add_argument('-covariate', required=True, help="name='regex' (title or text, case-insensitive)")
    parser.add_argument('-exclude', default='', help="leave terms matching this out of the printed lists")
    parser.add_argument('-outlet', action='store_true', help='add an outlet facet')
    parser.add_argument('-ngrams', default='2-3')
    parser.add_argument('-min-df', type=int, default=5)
    parser.add_argument('-max-vocab', type=int, default=20000, help='per language, before mapping')
    parser.add_argument('-threshold', type=float, default=0.7, help='Chinese -> English concept at this cosine')
    parser.add_argument('-min-uses', type=int, default=10, help='shared.tsv: uses in each language')
    parser.add_argument('-top', type=int, default=40)
    parser.add_argument('-experiment-name', required=True)
    return parser.parse_args()


def mapping_for(out, en_vocab, zh_vocab, threshold):
    """{Chinese unit: (concept, cosine)}, from mapping.tsv if it was made for these vocabularies."""
    key = hashlib.sha1('\n'.join(en_vocab + ['|'] + zh_vocab + [str(threshold), str(EMBED_VERSION)]).encode()
                       ).hexdigest()
    path, key_path = os.path.join(out, 'mapping.tsv'), os.path.join(out, 'mapping.key')
    if os.path.exists(path) and os.path.exists(key_path) and open(key_path).read().strip() == key:
        table = pd.read_csv(path, sep='\t', keep_default_na=False)
        print(f'mapping reused: {path}')
        return {w: (c, s) for w, c, s in zip(table['unit'], table['concept'], table['cosine'])}
    from src.dispersion.encoders import labse
    print(f'embedding {len(en_vocab)} English and {len(zh_vocab)} Chinese units (LaBSE)', flush=True)
    mapping = concept_map(en_vocab, zh_vocab, labse(), threshold, say=lambda line: print(line, flush=True))
    pd.DataFrame([{'unit': w, 'concept': c, 'cosine': round(s, 3)} for w, (c, s) in mapping.items()]).to_csv(
        path, sep='\t', index=False)
    with open(key_path, 'w') as f:
        f.write(key + '\n')
    return mapping


def main():
    args = parse_args()
    out = os.path.join(REPO_ROOT, 'results', NAME, args.experiment_name)
    os.makedirs(out, exist_ok=True)
    name, _, pattern = args.covariate.partition('=')
    regex = re.compile(pattern, re.I)
    docs = pd.read_parquet(args.docs)
    docs[name] = (docs['title'].fillna('') + '\n' + docs['text'].fillna('')).map(
        lambda t: 'yes' if regex.search(t) else 'no')
    stop = read_stopwords(STOPWORDS_EN_PATH)
    found, docs = doc_units(docs, parse_ns(args.ngrams), renderings=KnownRenderings.read(FIGHTIN_RENDERINGS_PATH),
                            stop=stop)
    print(pd.crosstab(docs['lang'], docs[name]).to_string(), flush=True)

    langs = docs['lang'].to_numpy()
    en_vocab = vocabulary([f for f, lang in zip(found, langs) if lang == 'en'], args.min_df, args.max_vocab)
    zh_vocab = vocabulary([f for f, lang in zip(found, langs) if lang == 'zh'], args.min_df, args.max_vocab)
    mapping = mapping_for(out, en_vocab, zh_vocab, args.threshold)
    concepts = to_concepts(found, langs, mapping, stop)
    vocab = vocabulary(concepts, args.min_df, 10 ** 9)
    X = count_matrix(concepts, vocab)
    mapped = sum(1 for c, s in mapping.values() if s >= args.threshold)
    print(f'{mapped}/{len(zh_vocab)} Chinese units mapped to an English concept; {len(vocab)} concepts', flush=True)

    docs['lang_x'] = docs['lang'] + '·' + docs[name]
    facets = {'lang': docs['lang'].to_numpy(), name: docs[name].to_numpy(), 'lang_x': docs['lang_x'].to_numpy()}
    if args.outlet:
        facets['outlet'] = docs['outlet'].to_numpy()
    model = AdditiveSAGE().fit(X, facets)
    print(', '.join(f'{f} sparsity {sparsity(e):.1%}' for f, e in model.eta.items()))

    base = model.component(name, 'yes') - model.component(name, 'no')
    table = pd.DataFrame({'concept': vocab})
    for lang in ('en', 'zh'):
        table[f'D_{lang}'] = (base + model.component('lang_x', f'{lang}·yes')
                              - model.component('lang_x', f'{lang}·no')).numpy()
        for value in ('yes', 'no'):
            rows = ((docs['lang'] == lang) & (docs[name] == value)).to_numpy()
            table[f'{lang}_{value}'] = np.asarray(X[rows].sum(0)).ravel().astype(int)
    table['gap'] = table['D_zh'] - table['D_en']
    forms = {}
    for unit, (concept, cosine) in mapping.items():
        if cosine >= args.threshold:
            forms.setdefault(concept, []).append(unit)
    table['zh_forms'] = table['concept'].map(lambda c: ' '.join(forms.get(c, [])[:3]))
    table = table.sort_values('gap', ascending=False).round(3)
    table.to_csv(os.path.join(out, 'compare.tsv'), sep='\t', index=False)
    used = (table['en_yes'] + table['en_no'] >= args.min_uses) & (table['zh_yes'] + table['zh_no'] >= args.min_uses)
    shared = table[used & ((table['D_en'].abs() > 0.01) | (table['D_zh'].abs() > 0.01))]
    shared.to_csv(os.path.join(out, 'shared.tsv'), sep='\t', index=False)

    show = shared[~shared['concept'].str.contains('|'.join(filter(None, [pattern, args.exclude])), case=False)]
    gaps = show[show['gap'].abs() > 0.01]
    both = show[(show['D_en'] > 1) & (show['D_zh'] > 1)].sort_values('D_en', ascending=False)
    for title, rows in ((f'more {name}-like in Chinese', gaps.head(args.top)),
                        (f'more {name}-like in English', gaps.tail(args.top)[::-1]),
                        (f'{name}-like in both', both.head(args.top))):
        print(f'\n=== {title}: concept [Chinese forms] D_en / D_zh (uses in {name} articles: en / zh)')
        print(', '.join(f"{r.concept}{f' [{r.zh_forms}]' if r.zh_forms else ''} {r.D_en:+.1f}/{r.D_zh:+.1f} "
                        f"({r.en_yes}/{r.zh_yes})" for r in rows.itertuples()))
    print(f"\n{len(shared)} concepts used in both languages -> {os.path.join(out, 'shared.tsv')}")


if __name__ == '__main__':
    main()
