"""Paths used across the project. Relative to the repo root, so scripts work from any directory."""
import os
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]

SEED_PATTERNS_PATH = REPO_ROOT / 'config' / 'seed_patterns.txt'
CC_LINKS_DIR = REPO_ROOT / 'data' / 'interim' / 'cc_links'
CC_LINK_MATCHES_PATH = REPO_ROOT / 'data' / 'processed' / 'cc_link_matches.jsonl'


def find_seed_links_work_dir():
    """$TMP/find_seed_links: downloaded WARCs and .lock/.done files. $TMP must be on shared storage."""
    if not os.environ.get('TMP'):
        raise EnvironmentError('$TMP is not set; set it or pass -work-dir')
    return Path(os.environ['TMP']) / 'find_seed_links'
