#!/usr/bin/env python
"""
Candidate links between English and Chinese media storms about the same event (src/storm_links.py): the Chinese
storm starts within a window around the English one, and they cite the same document or their titles are close
(LaBSE; Chinese names written in English first, as in fightin: 奥特曼 -> Altman).
    data/processed/storms_review.json, storms_review_zh.json (scripts/export_storms.py)
        -> data/processed/storm_links.tsv: one row per candidate pair, shared seeds first, then by similarity

Run as a module from the repo root:
    python -m scripts.link_storms
    python -m scripts.link_storms -en /tmp/storms/data/processed/storms_review.json \\
        -zh /tmp/storms/data/processed/storms_review_zh.json -out /tmp/storms/storm_links.tsv
"""
import argparse
import json
import os

import pandas as pd

from config.paths import FIGHTIN_RENDERINGS_PATH, NEWS_EN_ZH_LINKS_PATH
from src.fightin.renderings import KnownRenderings
from src.storm_links import candidate_links, storm_text

PROCESSED = os.path.dirname(str(NEWS_EN_ZH_LINKS_PATH))


def parse_args():
    parser = argparse.ArgumentParser(description='Link English and Chinese media storms')
    parser.add_argument('-en', default=os.path.join(PROCESSED, 'storms_review.json'))
    parser.add_argument('-zh', default=os.path.join(PROCESSED, 'storms_review_zh.json'))
    parser.add_argument('-out', default=os.path.join(PROCESSED, 'storm_links.tsv'))
    parser.add_argument('-min-similarity', type=float, default=0.5)
    parser.add_argument('-before', type=int, default=3, help='days the Chinese storm may start before the English')
    parser.add_argument('-after', type=int, default=14, help='days after the English storm ends')
    parser.add_argument('-top', type=int, default=3, help='English candidates per Chinese storm')
    return parser.parse_args()


def main():
    args = parse_args()
    en, zh = json.load(open(args.en)), json.load(open(args.zh))
    if not en or not zh:
        raise SystemExit(f'no storms in {args.en if not en else args.zh}: export them first (scripts/export_storms.py)')
    from src.dispersion.encoders import labse
    encode = labse()
    renderings = KnownRenderings.read(FIGHTIN_RENDERINGS_PATH)
    en_vecs = encode([storm_text(s) for s in en])
    zh_vecs = encode([renderings.apply(storm_text(s)) for s in zh])
    links = candidate_links(en, zh, en_vecs, zh_vecs, args.min_similarity, args.before, args.after, args.top)

    def side(storm, lang):
        return {f'{lang}_first': storm['first'], f'{lang}_articles': storm['n_articles'],
                f'{lang}_title': storm['title'], f'{lang}_cluster': storm['cluster']}
    rows = [{'similarity': round(lk['similarity'], 3), 'lag_days': lk['lag_days'],
             'shared_seeds': ' '.join(lk['shared_seeds']), **side(zh[lk['zh']], 'zh'), **side(en[lk['en']], 'en')}
            for lk in links]
    pd.DataFrame(rows).to_csv(args.out, sep='\t', index=False)
    linked = len({r['zh_cluster'] for r in rows})
    print(f'{len(en)} English and {len(zh)} Chinese storms; {linked} Chinese storms with a candidate '
          f'({len(rows)} pairs) -> {args.out}')
    for r in rows[:25]:
        seed = f"  seed {r['shared_seeds'][:60]}" if r['shared_seeds'] else ''
        print(f"  {r['similarity']:.2f}  {r['lag_days']:+3d}d  zh {r['zh_first']} {r['zh_title'][:40]}  <->  "
              f"en {r['en_first']} {r['en_title'][:50]}{seed}")


if __name__ == '__main__':
    main()
