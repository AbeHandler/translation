"""Paths used across the project. Relative to the repo root, so scripts work from any directory."""
import os
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]

SEED_PATTERNS_PATH = REPO_ROOT / 'config' / 'seed_patterns.txt'
CC_LINKS_DIR = REPO_ROOT / 'data' / 'interim' / 'cc_links'
CC_LINK_MATCHES_PATH = REPO_ROOT / 'data' / 'processed' / 'cc_link_matches.jsonl'
CC_HTML_DIR = REPO_ROOT / 'data' / 'interim' / 'cc_html'
CC_NEWS_EMBEDDINGS_DIR = REPO_ROOT / 'data' / 'interim' / 'cc_news_embeddings'  # src/news_embeddings.py
CC_NEWS_PUBDATES_DIR = REPO_ROOT / 'data' / 'interim' / 'cc_news_pubdates'  # src/news_pubdates.py
MEDIA_STORMS_DIR = REPO_ROOT / 'data' / 'interim' / 'media_storms'  # scripts/media_storms.py
MEDIA_STORMS_ZH_DIR = REPO_ROOT / 'data' / 'interim' / 'media_storms_zh'  # the same, over the Chinese site crawls
CC_NER_DIR = REPO_ROOT / 'data' / 'interim' / 'cc_ner'  # src/ner_html.py, one per cc_html file
# trained by scripts/train_quote_extractor.py (config/quote_extraction.yaml); not in git
QUOTE_MODEL_DIR = REPO_ROOT / 'results' / 'train_quote_extractor' / 'electra_small' / 'model'
GAZETTEER_PATH = REPO_ROOT / 'config' / 'gazetteer.yaml'
GAZETTEER_STORIES_PATH = REPO_ROOT / 'data' / 'processed' / 'gazetteer_stories.jsonl'
GAZETTEER_QUOTES_PATH = REPO_ROOT / 'data' / 'processed' / 'gazetteer_quotes.jsonl'  # scripts/extract_quotes.py
SITE_CRAWLS_DIR = REPO_ROOT / 'data' / 'interim' / 'site_crawls'  # scrapy/: <domain>/html, <domain>/embeddings
SITE_CRAWLS_ANNOY_DIR = REPO_ROOT / 'data' / 'processed' / 'site_crawls_annoy'
ENV_PATH = REPO_ROOT / '.env'  # API keys, e.g. XAI_API_KEY=...; gitignored
MT_SOURCES_CONFIG = REPO_ROOT / 'config' / 'mt_sources.yaml'
MT_SOURCES_DIR = REPO_ROOT / 'data' / 'raw' / 'mt_sources'  # <id>.html and <id>.txt per fetched source
WIKIPEDIA_CONFIG = REPO_ROOT / 'config' / 'wikipedia.yaml'
WIKIPEDIA_DIR = REPO_ROOT / 'data' / 'interim' / 'wikipedia'  # <lang>/pages/chunk_*.parquet, <lang>/ai_pages.parquet
NEWS_EN_ZH_LINKS_PATH = REPO_ROOT / 'data' / 'processed' / 'news_en_zh_links.jsonl'  # scripts/collect_queue.py
TRANSMISSION_PAIRS_PATH = REPO_ROOT / 'data' / 'processed' / 'transmission_pairs.csv'  # src/transmission
ZH_DOCS_PATH = REPO_ROOT / 'data' / 'processed' / 'zh_docs.jsonl'  # the fetched Chinese documents (src/zh_docs.py)
PRIMARY_SOURCES_DIR = REPO_ROOT / 'data' / 'interim' / 'primary_sources'  # scripts/primary_sources.py (cache)
PRIMARY_SOURCES_PATH = REPO_ROOT / 'data' / 'processed' / 'primary_sources.tsv'
SEEDS_PATH = REPO_ROOT / 'data' / 'processed' / 'seeds.tsv'  # main/step1/build_seeds.py
SEEDS_EXTRA_PATH = REPO_ROOT / 'config' / 'seeds_extra.tsv'  # hand-picked seeds, one URL per line
PRIMARY_TEXTS_DIR = REPO_ROOT / 'data' / 'interim' / 'primary'  # todo.tsv, <sha1 of the URL>.json (src/source_texts.py)
PRIMARY_DB_PATH = REPO_ROOT / 'data' / 'processed' / 'primary.pq'  # the store as one table (compile_primary_sources)
NOTABLE_ACCOUNTS_PATH = REPO_ROOT / 'data' / 'external' / 'notable_accounts.tsv'  # scripts/fetch_notable_accounts.py
NOTABLE_ACCOUNTS_EXTRA_PATH = REPO_ROOT / 'config' / 'notable_accounts_extra.tsv'  # hand-added, missing in Wikidata
ENGLISH_SCREENSHOTS_PATH = REPO_ROOT / 'data' / 'processed' / 'english_screenshot_links.tsv'
TRANSLATIONS_DB = REPO_ROOT / 'data' / 'processed' / 'translations.sqlite'  # src/translation/store.py


def warc_cache_dir():
    """Downloaded CC-NEWS WARCs, shared by every pipeline and kept (Alpine scratch purges old files)."""
    return _tmp_dir('cc_news_warcs')


def download_warcs_work_dir():
    """.lock/.done files of the CC-NEWS download step (scripts/cc_news_pipeline.py)."""
    return _tmp_dir('download_warcs')


def link_language_cache_dir():
    """Per-host language labels shared by the link_language queue workers (src/link_language/labeler.py)."""
    return _tmp_dir('link_language_cache')


def cc_full_dir():
    """The regular Common Crawl's English AI pages: warc_paths.txt and <warc>.ai.warc.gz (src/common_crawl_full)."""
    return _tmp_dir('cc_full')


def cc_full_queue_dir():
    """External links of the regular Common Crawl's English AI pages, as a shard queue (scripts/cc_full.py)."""
    return _tmp_dir('cc_full_queue')


def cc_news_queue_dir():
    """External links of CC-NEWS articles about AI, as a shard queue (scripts/cc_news_queue.py)."""
    return _tmp_dir('cc_news_queue')


def wikipedia_tmp_dir(name):
    """$TMP/wikipedia_<name>: dumps, queue, results (large, and fine to delete and rebuild)."""
    return _tmp_dir(f'wikipedia_{name}')


def news_similarity_weights_path():
    """The news-similarity model's weights (src/news_similarity.py), downloaded once."""
    return _tmp_dir('models') / 'newsSimilarity' / 'state_dict.tar'


def zh_docs_queue_dir():
    """The queue of linked Chinese pages to fetch as documents (scripts/zh_docs_queue.py, src/zh_docs.py)."""
    return _tmp_dir('zh_docs_queue')


def zh_docs_html_dir():
    """Raw HTML of the fetched Chinese documents, <sha1 of url>.html.gz (src/zh_docs.py)."""
    return _tmp_dir('zh_docs_html')


def extract_warc_html_work_dir():
    """.lock/.done files of the CC-NEWS html step (scripts/cc_news_pipeline.py)."""
    return _tmp_dir('extract_warc_html')


def _tmp_dir(name):
    """$TMP/<name>. $TMP must be on storage every node can see."""
    if not os.environ.get('TMP'):
        raise EnvironmentError(f'$TMP is not set; set it or pass the directory for {name} explicitly')
    return Path(os.environ['TMP']) / name
