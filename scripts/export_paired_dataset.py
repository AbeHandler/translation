#!/usr/bin/env python
"""
A shareable English/Chinese dataset on one topic, from a fightin experiment's sample (scripts/fightin.py: documents
matching a selection's pattern, English from CC-NEWS, Chinese from our site crawls): syndicated copies dropped
(src/fightin/contexts.py dedupe), optionally a date window -> results/export_paired_dataset/<name>/
    articles.parquet, articles.csv (utf-8 with BOM: opens in Excel), README.md (sources, counts, columns)

Run as a module from the repo root:
    python -m scripts.export_paired_dataset -experiment deepseek_20k -name deepseek_r1 -from 2025-01-15 -to 2025-02-28
    python -m scripts.export_paired_dataset -experiment deepseek_20k            # all dates
"""
import argparse
import datetime
import os

import pandas as pd

from config.paths import REPO_ROOT
from src.fightin.contexts import dedupe


def parse_args():
    parser = argparse.ArgumentParser(description='English/Chinese articles on one topic, for sharing')
    parser.add_argument('-experiment', required=True, help='results/fightin/<experiment>/docs.parquet')
    parser.add_argument('-name', default=None, help='output folder name (default: the experiment)')
    parser.add_argument('-from', dest='start', default=None, help='first date, YYYY-MM-DD')
    parser.add_argument('-to', dest='end', default=None, help='last date, YYYY-MM-DD')
    return parser.parse_args()


def select(docs, start, end):
    """Deduplicated documents within [start, end] (either may be None), sorted by language and date."""
    docs, dropped = dedupe(docs)
    dates = docs['date'].astype(str).str[:10]
    keep = (dates >= start if start else True) & (dates <= end if end else True)
    return docs[keep].sort_values(['lang', 'date']).reset_index(drop=True), dropped


def readme(docs, args, source, dropped):
    lines = [f'# {args.name or args.experiment}: English and Chinese news articles', '',
             f'Made {datetime.date.today()} from `{source}` (scripts/export_paired_dataset.py).',
             f'Dates: {args.start or "any"} to {args.end or "any"}. Syndicated copies dropped: {dropped}.', '',
             '- English: Common Crawl CC-NEWS pages tagged English that say "AI" at least twice; dates are crawl'
             ' dates.',
             '- Chinese: our crawls of mainland outlets, Chinese pages about AI; dates are publication dates.',
             '- Both match the topic pattern (config/fightin_selections.tsv) in title or text. Text is the main text '
             '(readability). A random sample, not every matching article.', '',
             '| lang | articles | outlets | first | last |', '|---|---|---|---|---|']
    for lang, g in docs.groupby('lang'):
        lines.append(f'| {lang} | {len(g)} | {g.outlet.nunique()} | {str(g.date.min())[:10]} | '
                     f'{str(g.date.max())[:10]} |')
    lines += ['', 'Columns: lang (en/zh), url, outlet, date, title, text.', '', 'Top outlets:', '']
    for lang, g in docs.groupby('lang'):
        top = ', '.join(f'{o} ({n})' for o, n in g.outlet.value_counts().head(10).items())
        lines.append(f'- {lang}: {top}')
    return '\n'.join(lines) + '\n'


def main():
    args = parse_args()
    source = os.path.join('results', 'fightin', args.experiment, 'docs.parquet')
    docs, dropped = select(pd.read_parquet(REPO_ROOT / source), args.start, args.end)
    out = REPO_ROOT / 'results' / 'export_paired_dataset' / (args.name or args.experiment)
    os.makedirs(out, exist_ok=True)
    docs.to_parquet(out / 'articles.parquet', index=False)
    docs.to_csv(out / 'articles.csv', index=False, encoding='utf-8-sig')
    (out / 'README.md').write_text(readme(docs, args, source, dropped), encoding='utf-8')
    print((out / 'README.md').read_text(encoding='utf-8'))
    print(f'-> {out}/ (articles.parquet, articles.csv, README.md)')
    print(f'Spot check: python -c "import pandas as pd; d = pd.read_parquet(\'{out}/articles.parquet\'); '
          f'print(d.groupby(\'lang\').sample(2)[[\'lang\', \'outlet\', \'date\', \'title\']])"')


if __name__ == '__main__':
    main()
