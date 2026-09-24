"""Paths used across the project. Relative to the repo root, so scripts work from any directory."""
import os
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]

SEED_PATTERNS_PATH = REPO_ROOT / 'config' / 'seed_patterns.txt'
CC_LINKS_DIR = REPO_ROOT / 'data' / 'interim' / 'cc_links'
CC_LINK_MATCHES_PATH = REPO_ROOT / 'data' / 'processed' / 'cc_link_matches.jsonl'
CC_HTML_DIR = REPO_ROOT / 'data' / 'interim' / 'cc_html'
SITE_CRAWLS_DIR = REPO_ROOT / 'data' / 'interim' / 'site_crawls'  # scrapy/: <domain>/html, <domain>/embeddings
SITE_CRAWLS_ANNOY_DIR = REPO_ROOT / 'data' / 'processed' / 'site_crawls_annoy'
ENV_PATH = REPO_ROOT / '.env'  # API keys, e.g. XAI_API_KEY=...; gitignored
TRANSLATIONS_DB = REPO_ROOT / 'data' / 'processed' / 'translations.sqlite'  # src/translation/store.py


def warc_cache_dir():
    """Downloaded CC-NEWS WARCs, shared by every pipeline and kept (Alpine scratch purges old files)."""
    return _tmp_dir('cc_news_warcs')


def find_seed_links_work_dir():
    return _tmp_dir('find_seed_links')


def extract_warc_html_work_dir():
    return _tmp_dir('extract_warc_html')


def _tmp_dir(name):
    """$TMP/<name>. $TMP must be on storage every node can see."""
    if not os.environ.get('TMP'):
        raise EnvironmentError(f'$TMP is not set; set it or pass the directory for {name} explicitly')
    return Path(os.environ['TMP']) / name
