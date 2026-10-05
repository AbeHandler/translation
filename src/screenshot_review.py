"""
Reviewing English screenshots by eye (scripts/review_screenshots.py): which screenshots in the export to show next,
and the decisions so far, kept in a YAML file ({src: {decision: keep|discard, page, kind, site, date, accounts,
reviewed_at}}) so a review can stop and resume. Logic only.
"""
import csv
import datetime
import os
import random

import yaml

FIELDS = ('page', 'kind', 'site', 'date', 'accounts')


def load_screenshots(tsv_path, notable_only=False, seed=0):
    """The export's rows, each image once, in a random (seeded) order; notable_only keeps notable ones."""
    with open(tsv_path, encoding='utf-8', newline='') as f:
        rows = [r for r in csv.DictReader(f, delimiter='\t') if not notable_only or r['notable'] == '1']
    rows = list({r['src']: r for r in rows}.values())
    random.Random(seed).shuffle(rows)
    return rows


def load_decisions(path):
    if not os.path.exists(path):
        return {}
    with open(path, encoding='utf-8') as f:
        return yaml.safe_load(f) or {}


def save_decisions(path, decisions):
    """Write the YAML file whole, via .part, so an interrupted save never leaves it half written."""
    with open(path + '.part', 'w', encoding='utf-8') as f:
        yaml.safe_dump(decisions, f, allow_unicode=True, sort_keys=False)
    os.replace(path + '.part', path)


def record(decisions, row, decision):
    decisions[row['src']] = {'decision': decision, **{k: row.get(k, '') for k in FIELDS},
                             'reviewed_at': datetime.datetime.now().isoformat(timespec='seconds')}


def next_batch(rows, decisions, size=6):
    """The next size rows without a decision."""
    return [r for r in rows if r['src'] not in decisions][:size]
