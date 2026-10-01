"""
Working with CC-NEWS. Logic only: no paths, no command line. Three steps (scripts/cc_news_pipeline.py), each
reading only the previous step's output, so only the first touches the (1GB) WARCs:
    html   WARC -> <html_dir>/<warc>.parquet: raw HTML of every en/zh article (ArticleHtmlArchiver), the same
           format as the site crawls' html/*.parquet. HtmlArchivePipeline: many workers coordinate through
           <work_dir>/<warc>.lock and <warc>.done; WARCs are fetched into a cache and kept.
    links  <warc>.parquet -> <links_dir>/<warc>.jsonl: each article's body links (ArticleLinkExtractor;
           readability drops nav, footer and sidebar links). Workers: src/file_worker.py.
    match  every links file of the date range -> the links containing a seed pattern (match_seed_links),
           also inside URL-encoded redirect links. Checks first that every WARC in the range has its links.

Each step skips work already done, so a rerun picks up where the last one stopped. Work dirs and the WARC
cache must be on a filesystem every node can see. max_n (rows per WARC, for tests) adds .max<N> to every file
name, so test runs never mix with real ones.
"""
import datetime
import glob
import json
import logging
import os
import random
import socket
import subprocess
import time
from collections import Counter
from contextlib import contextmanager
from dataclasses import dataclass
from types import SimpleNamespace
from urllib.parse import unquote, urljoin, urlparse

import lxml.html
from newsplease.pipeline.extractor.extractors.lang_detect_extractor import LangExtractor
from readability import Document
from tqdm import tqdm
from tqdm.utils import CallbackIOWrapper
import pyarrow as pa
import pyarrow.parquet as pq
from warcio.archiveiterator import ArchiveIterator

from src.ai_mentions import mentions_ai, mentions_ai_html
from src.external_links import external_links
from src.file_worker import claim_lock, slurm_job_id

S3_BUCKET = 's3://commoncrawl/'

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------- listing and downloading WARCs

class CCNewsIndex:
    """Lists CC-NEWS WARCs on s3://commoncrawl and fetches them into a local cache (aws CLI).
    Cached WARCs are never deleted here, so any pipeline can reuse them without downloading again.

    A WARC is named by its S3 key: crawl-data/CC-NEWS/2026/09/CC-NEWS-20260923153007-00006.warc.gz
    """

    # Common Crawl answers too many requests with "SlowDown" (HTTP 503); these are worth retrying.
    THROTTLE_MESSAGES = ('SlowDown', 'reduce your request rate', 'Throttling', '503')
    # Inside each aws call: adaptive mode slows down the client itself when it gets throttled.
    AWS_RETRY_ENV = {'AWS_RETRY_MODE': 'adaptive', 'AWS_MAX_ATTEMPTS': '10'}

    def __init__(self, cache_dir, aws='aws', bucket=S3_BUCKET, max_tries=8, max_wait_seconds=600):
        self.cache_dir = cache_dir
        self.aws = aws
        self.bucket = bucket
        self.max_tries = max_tries
        self.max_wait_seconds = max_wait_seconds
        os.makedirs(cache_dir, exist_ok=True)

    def list_warcs(self, start_date, end_date):
        """Keys of the WARCs crawled on days in [start_date, end_date]."""
        keys = []
        for year, month in months_between(start_date, end_date):
            keys += self._list_month(year, month)
        return [key for key in keys if start_date <= warc_date(key) <= end_date]

    def cached_path(self, key):
        return os.path.join(self.cache_dir, os.path.basename(key))

    def fetch(self, key):
        """Local path of the WARC, downloading it into the cache first if it isn't there."""
        path = self.cached_path(key)
        if not os.path.exists(path):
            # A .part name unique to this process: if two workers (e.g. both pipelines) fetch the
            # same WARC at once, each downloads to its own file and the rename is atomic.
            part = f'{path}.{socket.gethostname()}.{os.getpid()}.part'
            self._aws('s3', 'cp', '--only-show-errors', self.bucket + key, part)
            os.rename(part, path)
        return path

    def _list_month(self, year, month):
        # `aws s3 ls` prints lines like: 2026-09-23 16:01:02 1072866466 CC-NEWS-20260923153007-00006.warc.gz
        prefix = f'crawl-data/CC-NEWS/{year}/{month:02d}/'
        listing = self._aws('s3', 'ls', self.bucket + prefix)
        return [prefix + line.split()[-1] for line in listing.splitlines() if line.endswith('.warc.gz')]

    def _aws(self, *args):
        """
        Run the aws CLI and return its stdout. When S3 throttles us, wait and try again, up to
        max_tries times; the wait doubles each time and is random, so many workers don't retry in
        lockstep. Any other failure, or throttling that never lets up, raises with aws's stderr.
        """
        env = {**os.environ, **self.AWS_RETRY_ENV}
        for attempt in range(1, self.max_tries + 1):
            result = subprocess.run([self.aws, *args], capture_output=True, text=True, env=env)
            if result.returncode == 0:
                return result.stdout
            throttled = any(message in result.stderr for message in self.THROTTLE_MESSAGES)
            if not throttled or attempt == self.max_tries:
                break
            wait = random.uniform(0, min(self.max_wait_seconds, 30 * 2 ** attempt))
            logger.info('S3 throttled (try %d of %d); waiting %.0fs', attempt, self.max_tries, wait)
            time.sleep(wait)
        raise RuntimeError(f'{self.aws} {" ".join(args)} failed after {attempt} tries:\n{result.stderr}')


def warc_name(key):
    """crawl-data/.../CC-NEWS-20260923153007-00006.warc.gz -> CC-NEWS-20260923153007-00006"""
    return os.path.basename(key).removesuffix('.warc.gz')


def warc_date(key):
    """crawl-data/.../CC-NEWS-20260923153007-00006.warc.gz -> date(2026, 9, 23)"""
    timestamp = warc_name(key).split('-')[2]
    return datetime.datetime.strptime(timestamp[:8], '%Y%m%d').date()


def months_between(start_date, end_date):
    """Yield (year, month) for every month from start_date to end_date, inclusive."""
    first_of_month = start_date.replace(day=1)
    while first_of_month <= end_date:
        yield first_of_month.year, first_of_month.month
        next_month = first_of_month + datetime.timedelta(days=32)  # always lands in the next month
        first_of_month = next_month.replace(day=1)


# ---------------------------------------------------------------- extracting article links

class NewsPleaseLanguage:
    """A page's language as news-please sees it: <html lang>, then meta tags, then langdetect."""

    def __init__(self):
        self._extractor = LangExtractor()

    def __call__(self, html):
        # Only news-please's language extractor; its full pipeline is much slower.
        return self._extractor._language({'spider_response': SimpleNamespace(body=html)})


LANGUAGES = ('en', 'zh')  # news-please two-letter codes; zh covers zh-cn, zh-tw, zh-hk, ...


class ArticleLinkExtractor:
    """Turns an HTML Parquet file (ArticleHtmlArchiver's) into one row per article:
        {url, title, language, record_id, ai_mentions, body_ai_mentions, n_links, links: [{href, text, internal}]}
        (ai_mentions: "AI" in the page's visible text; body_ai_mentions: in the article body only)
    ai_mentions: times the page's visible text says "AI" (src/ai_mentions.py), for the link queue.

    readability trims each page to the article body, so nav/footer/sidebar links are dropped.
    """

    SKIP_HREF_PREFIXES = ('#', 'javascript:', 'mailto:', 'tel:')
    BATCH_ROWS = 200  # pages read at a time, so a whole file's HTML never sits in memory

    def __init__(self):
        self.counts = Counter()

    def write(self, html_path, out_path):
        """Write out_path (atomically). Returns the counts."""
        write_jsonl(out_path, self.rows(html_path))
        return dict(self.counts)

    def rows(self, html_path):
        """Yield a row per parseable page. Tallies self.counts."""
        self.counts = Counter(rows=0, links=0, errors=0, bad_hrefs=0)
        parquet = pq.ParquetFile(html_path)
        for batch in parquet.iter_batches(batch_size=self.BATCH_ROWS, columns=['url', 'language', 'record_id', 'html']):
            for page in batch.to_pylist():
                row = self.row(page)
                if row is None:
                    continue
                self.counts['rows'] += 1
                self.counts['links'] += row['n_links']
                yield row

    def row(self, page):
        """The row for one page ({url, language, record_id, html}), or None if it can't be parsed."""
        try:
            doc = Document(page['html'])
            title, body = doc.short_title(), lxml.html.fromstring(doc.summary())
        except Exception as exc:  # empty/garbled pages are common in CC-NEWS
            self.counts['errors'] += 1
            logger.debug('parse failed for %s: %s', page['url'], exc)
            return None
        links = self._links(page['url'], body)
        return {'url': page['url'], 'title': title, 'language': page['language'], 'record_id': page['record_id'],
                'ai_mentions': mentions_ai_html(page['html'])[0], 'body_ai_mentions': mentions_ai(body.text_content()),
                'n_links': len(links), 'links': links}

    def _links(self, page_url, body):
        """Links in the article body, with relative hrefs made absolute. Unparseable hrefs are skipped."""
        links = []
        for anchor in body.iter('a'):
            href = anchor.get('href', '').strip()
            if not href or href.startswith(self.SKIP_HREF_PREFIXES):
                continue
            try:
                href = urljoin(page_url, href)
                internal = urlparse(href).netloc == urlparse(page_url).netloc
            except ValueError:  # malformed hrefs in the wild, e.g. 'http://[broken'
                self.counts['bad_hrefs'] += 1
                continue
            links.append({'href': href, 'text': anchor.text_content().strip(), 'internal': internal})
        return links


@dataclass
class HtmlPage:
    url: str
    html: bytes         # as served, undecoded
    content_type: str   # HTTP Content-Type, e.g. 'text/html; charset=utf-8'
    warc_date: str      # when Common Crawl fetched it, e.g. '2026-09-23T15:30:07Z'
    record_id: str      # WARC-Record-ID, unique per capture


def iter_html_pages(warc_stream):
    """Yield an HtmlPage for each HTML response in an open WARC stream."""
    for record in ArchiveIterator(warc_stream):
        if record.rec_type != 'response':
            continue
        content_type = record.http_headers.get_header('Content-Type') or ''
        if 'html' not in content_type:
            continue
        yield HtmlPage(url=record.rec_headers.get_header('WARC-Target-URI'),
                       html=record.content_stream().read(),
                       content_type=content_type,
                       warc_date=record.rec_headers.get_header('WARC-Date'),
                       record_id=record.rec_headers.get_header('WARC-Record-ID'))


# ---------------------------------------------------------------- archiving article HTML

class ArticleHtmlArchiver:
    """Writes the raw HTML of every page in the wanted languages to one zstd-compressed Parquet
    file per WARC, for parsing later (e.g. newspaper for text, title, date)."""

    SCHEMA = pa.schema([
        ('url', pa.string()),
        ('language', pa.string()),
        ('warc_date', pa.string()),
        ('content_type', pa.string()),
        ('record_id', pa.string()),
        ('html', pa.binary()),
    ])
    ROWS_PER_GROUP = 1000  # write in batches so a whole WARC never sits in memory

    def __init__(self, languages=LANGUAGES, max_n=None):
        self.languages = languages
        self.max_n = max_n
        self.counts = Counter()
        self._language = NewsPleaseLanguage()

    def write(self, warc_stream, out_path):
        """Write the Parquet file (via .part, so a partial file never looks done). Returns the counts."""
        self.counts = Counter(rows=0, html_bytes=0, other_language=0, errors=0)
        with pq.ParquetWriter(out_path + '.part', self.SCHEMA, compression='zstd') as writer:
            batch = []
            for row in self._rows(warc_stream):
                batch.append(row)
                if len(batch) == self.ROWS_PER_GROUP:
                    writer.write_table(pa.Table.from_pylist(batch, self.SCHEMA))
                    batch = []
            if batch:
                writer.write_table(pa.Table.from_pylist(batch, self.SCHEMA))
        os.rename(out_path + '.part', out_path)
        return dict(self.counts)

    def _rows(self, warc_stream):
        for page in iter_html_pages(warc_stream):
            try:
                language = self._language(page.html)
            except Exception as exc:  # empty/garbled pages are common in CC-NEWS
                self.counts['errors'] += 1
                logger.debug('language failed for %s: %s', page.url, exc)
                continue
            if language not in self.languages:
                self.counts['other_language'] += 1
                continue
            self.counts['rows'] += 1
            self.counts['html_bytes'] += len(page.html)
            yield {'url': page.url, 'language': language, 'warc_date': page.warc_date,
                   'content_type': page.content_type, 'record_id': page.record_id, 'html': page.html}
            if self.max_n and self.counts['rows'] >= self.max_n:
                return


@contextmanager
def open_with_progress(path):
    """Open a file for reading with a tqdm bar over its bytes (no bar when not a terminal, e.g. SLURM)."""
    with open(path, 'rb') as f, \
            tqdm(total=os.path.getsize(path), unit='B', unit_scale=True, desc=os.path.basename(path),
                 disable=None) as bar:
        yield CallbackIOWrapper(bar.update, f, 'read')


# ---------------------------------------------------------------- coordinating workers

class WorkDir:
    """Shared directory where one pipeline's workers coordinate:
        <warc>.lock           claimed by a worker (host and job id inside)
        <warc>.done           finished; one line of JSON with the counts
    """

    def __init__(self, path, max_n=None):
        self.path = path
        self.max_n = max_n
        os.makedirs(path, exist_ok=True)

    def is_done(self, key):
        return os.path.exists(self._marker(key, '.done'))

    def claim(self, key):
        return claim_lock(self._marker(key, '.lock'))

    def release(self, key):
        os.remove(self._marker(key, '.lock'))

    def mark_done(self, key, info):
        with atomic_write(self._marker(key, '.done')) as f:
            f.write(json.dumps(info) + '\n')

    def _marker(self, key, suffix):
        return os.path.join(self.path, with_max_n(warc_name(key), self.max_n) + suffix)


# ---------------------------------------------------------------- grepping for seed links

def read_patterns(path):
    """One substring per line; blank lines and # comments are skipped."""
    with open(path) as f:
        patterns = [line.strip() for line in f if line.strip() and not line.startswith('#')]
    if not patterns:
        raise ValueError(f'no patterns in {path}')
    return patterns


def grep_links(paths, patterns):
    """Yield one row per (article link, pattern) where the pattern is in the href, as written or URL-decoded
    (redirect links carry their target encoded: link.zhihu.com/?target=https%3A%2F%2Fdarioamodei.com%2F...);
    decoded says which."""
    hosts = {pattern.split('/')[0] for pattern in patterns}  # dots survive URL-encoding; slashes don't
    for path in paths:
        with open(path, encoding='utf-8') as f:
            for line in f:
                if not any(host in line for host in hosts):  # skip the json parse for most lines
                    continue
                article = json.loads(line)
                for link in article['links']:
                    href = link['href']
                    decoded = unquote(unquote(href))
                    for pattern in patterns:
                        if pattern in href or pattern in decoded:
                            yield {'pattern': pattern, 'href': href, 'decoded': pattern not in href,
                                   'link_text': link['text'], 'url': article['url'], 'title': article['title'],
                                   'language': article['language'], 'links_file': os.path.basename(path)}


def ai_articles(html_path, min_ai_mentions=1):
    """(record_ids, urls) of the pages in an HTML file whose visible text says "AI" at least min_ai_mentions
    times (src/ai_mentions.py). Read in batches, so a whole file's HTML never sits in memory."""
    ids, urls = set(), set()
    for batch in pq.ParquetFile(html_path).iter_batches(batch_size=500, columns=['record_id', 'url', 'html']):
        for record_id, url, html in zip(*batch.to_pydict().values()):
            if mentions_ai_html(html)[0] >= min_ai_mentions:
                ids.add(record_id)
                urls.add(url)
    return ids, urls


def ai_article_links(html_path, links_path, min_ai_mentions=1):
    """{srcpage, src_language, url} for each external body link (src/external_links.py) of the articles in one
    WARC whose visible text says "AI" at least min_ai_mentions times; src_language is the article's language
    (news-please, in the links file). Links files record the "AI" count (ai_mentions); for older ones without it,
    it is worked out from the HTML file (slower), joined on record_id, or on url for the oldest links files, made
    before they had record_id. Needs only the html and links steps, not NER."""
    ids = urls = None
    with open(links_path, encoding='utf-8') as f:
        for line in f:
            article = json.loads(line)
            if 'ai_mentions' in article:
                is_ai = article['ai_mentions'] >= min_ai_mentions
            else:
                if ids is None:
                    ids, urls = ai_articles(html_path, min_ai_mentions)
                is_ai = article['record_id'] in ids if 'record_id' in article else article['url'] in urls
            if not is_ai:
                continue
            for href in external_links(article['url'], (link['href'] for link in article['links'])):
                yield {'srcpage': article['url'], 'src_language': article.get('language'), 'url': href}


def match_seed_links(keys, links_path_of, patterns, matches_path, partial=False):
    """Write every seed-pattern match in the links files of these WARC keys to matches_path. Unless partial,
    first check that every WARC has its links file, so the matches cover the whole date range. Returns the
    number of matches per pattern."""
    paths = [links_path_of(key) for key in keys]
    missing = [path for path in paths if not os.path.exists(path)]
    if missing and not partial:
        raise FileNotFoundError(f'{len(missing)} of {len(paths)} WARCs have no links file yet (e.g. {missing[0]}); '
                                'run the html and links steps first, or pass -partial')
    matches = list(grep_links([path for path in paths if os.path.exists(path)], patterns))
    os.makedirs(os.path.dirname(matches_path), exist_ok=True)
    write_jsonl(matches_path, matches)
    return Counter(match['pattern'] for match in matches)


# ---------------------------------------------------------------- small helpers

@contextmanager
def atomic_write(path):
    """Write to path.part and rename it to path only if the block finishes, so a partial file never looks done."""
    with open(path + '.part', 'w', encoding='utf-8') as f:
        yield f
    os.rename(path + '.part', path)


def write_jsonl(path, rows):
    with atomic_write(path) as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False) + '\n')


def warc_files(directory, ext, start_date, end_date, max_n=None):
    """Files <directory>/<warc name>[.max<N>]<ext> of WARCs crawled in [start_date, end_date]: test files
    (.max<N>) only when max_n is given, and then only those."""
    paths = []
    for path in sorted(glob.glob(os.path.join(directory, '*' + ext))):
        name = os.path.basename(path).removesuffix(ext)
        suffix = f'.max{max_n}' if max_n else ''
        if (suffix and not name.endswith(suffix)) or (not suffix and '.max' in name):
            continue
        if start_date <= warc_date(name.removesuffix(suffix)) <= end_date:
            paths.append(path)
    return paths


def with_max_n(name, max_n):
    """'a' -> 'a.max100' and 'a.jsonl' -> 'a.max100.jsonl' for test runs; unchanged when max_n is None."""
    if not max_n:
        return name
    stem, ext = os.path.splitext(name)
    return f'{stem}.max{max_n}{ext}'


# ---------------------------------------------------------------- the pipeline

PROGRESS_EVERY = 10  # WARCs; counting what's left stats every .done file, so not after each one


class WarcWorker:
    """The html step's loop: for each WARC not done and not claimed by another worker
    (in random order), fetch it (from the cache, or download it), run process(key, local_warc) -> info,
    and write info to its .done file. Many workers can run at once; they coordinate through work_dir."""

    def __init__(self, index, work_dir, max_warcs=None):
        self.index = index
        self.work_dir = work_dir
        self.max_warcs = max_warcs

    def list_warcs(self, start_date, end_date):
        keys = self.index.list_warcs(start_date, end_date)
        if not keys:
            raise ValueError(f'no CC-NEWS WARCs between {start_date} and {end_date}')
        logger.info('%d WARCs between %s and %s; %d not done yet',
                    len(keys), start_date, end_date, self.n_not_done(keys))
        return keys

    def n_not_done(self, keys):
        return sum(not self.work_dir.is_done(key) for key in keys)

    def process_all(self, keys, process):
        todo = [key for key in keys if not self.work_dir.is_done(key)]
        random.shuffle(todo)
        logger.info('%d of %d WARCs to do; this worker starts at a random point in them', len(todo), len(keys))
        n_processed = 0
        started = time.time()
        for key in todo:
            if self.work_dir.is_done(key) or not self.work_dir.claim(key):
                continue
            try:
                self._process_one(key, process)
            finally:
                self.work_dir.release(key)  # also on failure, so a rerun can pick the WARC up
            n_processed += 1
            if n_processed % PROGRESS_EVERY == 0:
                logger.info('progress: this worker did %d WARCs (%.1f min each); %d of %d left in the range',
                            n_processed, (time.time() - started) / n_processed / 60, self.n_not_done(keys),
                            len(keys))
            if self.max_warcs and n_processed >= self.max_warcs:
                break
        logger.info('this worker processed %d WARCs', n_processed)

    def _process_one(self, key, process):
        cached = os.path.exists(self.index.cached_path(key))
        started = time.time()
        local_warc = self.index.fetch(key)
        fetched = time.time()
        info = process(key, local_warc)
        self.work_dir.mark_done(key, {'warc': key, **info, 'finished_at': datetime.datetime.now().isoformat(),
                                      'host': socket.gethostname(), 'slurm_job_id': slurm_job_id()})
        logger.info('done %s (%s in %.0fs, processed in %.0fs) %s', warc_name(key),
                    'from cache' if cached else 'downloaded', fetched - started, time.time() - fetched, info)


class HtmlArchivePipeline:
    """The html step: one Parquet file of raw en/zh article HTML per WARC in a date range."""

    def __init__(self, worker, archiver, output_dir):
        self.worker = worker
        self.archiver = archiver
        self.output_dir = output_dir
        os.makedirs(output_dir, exist_ok=True)

    def run(self, start_date, end_date):
        keys = self.worker.list_warcs(start_date, end_date)
        self.worker.process_all(keys, self.extract_html)
        logger.info('%d WARCs not done yet (other workers, or -max-warcs)', self.worker.n_not_done(keys))

    def extract_html(self, key, local_warc):
        out_path = os.path.join(self.output_dir, with_max_n(warc_name(key), self.worker.work_dir.max_n) + '.parquet')
        with open_with_progress(local_warc) as stream:
            counts = self.archiver.write(stream, out_path)
        return {'output': out_path, **counts}
