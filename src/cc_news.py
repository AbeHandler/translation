#!/usr/bin/env python
"""
Find which CC-NEWS articles link to a set of seed URLs.

SeedLinkPipeline.run(start_date, end_date) runs every step; each one skips work already done,
so a rerun picks up where the last one stopped:
    1. list the WARCs crawled in [start_date, end_date] that have no .done file yet
    2. for each of them (shuffled) that no other worker has claimed: download it, write one row
       per en/zh article with the links in its body -> <output-dir>/<warc>.jsonl, mark it done,
       delete the WARC
    3. once every WARC in the range is done, find article links containing a line of
       config/seed_patterns.txt -> data/processed/cc_link_matches.jsonl

Run many copies at once (scripts/go.sh does): they coordinate through
<work-dir>/<warc>.lock and <warc>.done files, so -work-dir must be on a filesystem every node
can see. Whichever copy finishes last writes the matches. -max-n (rows per WARC, for tests)
adds .max<N> to every file name, so test runs never mix with real ones.
scripts/flush.sh deletes everything this writes, for a clean rerun.

Usage:
    python src/cc_news.py -start-date 20260901 -end-date 20260923
    python src/cc_news.py -start-date 20260923 -end-date 20260923 -max-warcs 1 -max-n 100
"""
import argparse
import datetime
import json
import logging
import os
import random
import socket
import subprocess
from collections import Counter
from contextlib import contextmanager
from types import SimpleNamespace
from urllib.parse import urljoin, urlparse

import lxml.html
from newsplease.pipeline.extractor.extractors.lang_detect_extractor import LangExtractor
from readability import Document
from tqdm import tqdm
from tqdm.utils import CallbackIOWrapper
from warcio.archiveiterator import ArchiveIterator

DEFAULT_OUTPUT_DIR = 'data/interim/cc_links'
DEFAULT_MATCHES_PATH = 'data/processed/cc_link_matches.jsonl'
DEFAULT_PATTERNS = 'config/seed_patterns.txt'
S3_BUCKET = 's3://commoncrawl/'

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------- listing and downloading WARCs

class CCNewsIndex:
    """Lists and downloads CC-NEWS WARCs from s3://commoncrawl with the aws CLI.

    A WARC is named by its S3 key: crawl-data/CC-NEWS/2026/09/CC-NEWS-20260923153007-00006.warc.gz
    """

    def __init__(self, aws='aws', bucket=S3_BUCKET):
        self.aws = aws
        self.bucket = bucket

    def list_warcs(self, start_date, end_date):
        """Keys of the WARCs crawled on days in [start_date, end_date]."""
        keys = []
        for year, month in months_between(start_date, end_date):
            keys += self._list_month(year, month)
        return [key for key in keys if start_date <= warc_date(key) <= end_date]

    def download(self, key, dest):
        """Download via a .part file, so a killed download never looks complete."""
        self._aws('s3', 'cp', '--only-show-errors', self.bucket + key, dest + '.part')
        os.rename(dest + '.part', dest)

    def _list_month(self, year, month):
        # `aws s3 ls` prints lines like: 2026-09-23 16:01:02 1072866466 CC-NEWS-20260923153007-00006.warc.gz
        prefix = f'crawl-data/CC-NEWS/{year}/{month:02d}/'
        listing = self._aws('s3', 'ls', self.bucket + prefix)
        return [prefix + line.split()[-1] for line in listing.splitlines() if line.endswith('.warc.gz')]

    def _aws(self, *args):
        """Run the aws CLI and return its stdout; raise with its stderr on failure."""
        result = subprocess.run([self.aws, *args], capture_output=True, text=True)
        if result.returncode != 0:
            raise RuntimeError(f'{self.aws} {" ".join(args)} failed:\n{result.stderr}')
        return result.stdout


def warc_name(key):
    """crawl-data/.../CC-NEWS-20260923153007-00006.warc.gz -> CC-NEWS-20260923153007-00006"""
    return os.path.basename(key).removesuffix('.warc.gz')


def warc_date(key):
    """crawl-data/.../CC-NEWS-20260923153007-00006.warc.gz -> date(2026, 9, 23)"""
    timestamp = warc_name(key).split('-')[2]
    return datetime.datetime.strptime(timestamp[:8], '%Y%m%d').date()


def months_between(start_date, end_date):
    """Yield (year, month) for every month from start_date to end_date, inclusive."""
    year, month = start_date.year, start_date.month
    while (year, month) <= (end_date.year, end_date.month):
        yield year, month
        year, month = (year + 1, 1) if month == 12 else (year, month + 1)


# ---------------------------------------------------------------- extracting article links

class ArticleLinkExtractor:
    """Turns a WARC into one row per article in the wanted languages:
        {url, title, language, n_links, links: [{href, text, internal}]}

    The language comes from news-please (<html lang>, then meta tags, then langdetect).
    readability trims each page to the article body, so nav/footer/sidebar links are dropped.
    """

    LANGUAGES = ('en', 'zh')  # news-please two-letter codes; zh covers zh-cn, zh-tw, zh-hk, ...
    SKIP_HREF_PREFIXES = ('#', 'javascript:', 'mailto:', 'tel:')

    def __init__(self, languages=LANGUAGES, max_n=None):
        self.languages = languages
        self.max_n = max_n
        self.counts = Counter()
        self._lang_extractor = LangExtractor()

    def rows(self, warc_stream):
        """Yield rows from an open .warc.gz stream (at most max_n). Tallies self.counts."""
        self.counts = Counter(rows=0, links=0, other_language=0, errors=0)
        for url, html in iter_html_pages(warc_stream):
            row = self._row(url, html)
            if row is None:
                continue
            self.counts['rows'] += 1
            self.counts['links'] += row['n_links']
            yield row
            if self.max_n and self.counts['rows'] >= self.max_n:
                return

    def _row(self, url, html):
        """The row for one page, or None if it is in another language or can't be parsed."""
        try:
            language = self._language(html)
            if language not in self.languages:
                self.counts['other_language'] += 1
                return None
            doc = Document(html)
            title, body = doc.short_title(), lxml.html.fromstring(doc.summary())
        except Exception as exc:  # empty/garbled pages are common in CC-NEWS
            self.counts['errors'] += 1
            logger.debug('parse failed for %s: %s', url, exc)
            return None
        links = self._links(url, body)
        return {'url': url, 'title': title, 'language': language, 'n_links': len(links), 'links': links}

    def _language(self, html):
        # Only news-please's language extractor; its full pipeline is much slower.
        return self._lang_extractor._language({'spider_response': SimpleNamespace(body=html)})

    def _links(self, page_url, body):
        """Links in the article body, with relative hrefs made absolute."""
        links = []
        for anchor in body.iter('a'):
            href = anchor.get('href', '').strip()
            if not href or href.startswith(self.SKIP_HREF_PREFIXES):
                continue
            href = urljoin(page_url, href)
            links.append({
                'href': href,
                'text': anchor.text_content().strip(),
                'internal': urlparse(href).netloc == urlparse(page_url).netloc,
            })
        return links


def iter_html_pages(warc_stream):
    """Yield (url, html_bytes) for each HTML response in an open WARC stream."""
    for record in ArchiveIterator(warc_stream):
        if record.rec_type != 'response':
            continue
        if 'html' not in (record.http_headers.get_header('Content-Type') or ''):
            continue
        yield record.rec_headers.get_header('WARC-Target-URI'), record.content_stream().read()


@contextmanager
def open_with_progress(path):
    """Open a file for reading with a tqdm bar over its bytes (no bar when not a terminal, e.g. SLURM)."""
    with open(path, 'rb') as f, \
            tqdm(total=os.path.getsize(path), unit='B', unit_scale=True, desc=os.path.basename(path),
                 disable=None) as bar:
        yield CallbackIOWrapper(bar.update, f, 'read')


# ---------------------------------------------------------------- coordinating workers

class WorkDir:
    """Shared directory where workers coordinate:
        <warc>.warc.gz        a download in progress
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
        """Create the .lock file; False if another worker already has it (O_EXCL makes this atomic)."""
        try:
            fd = os.open(self._marker(key, '.lock'), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        except FileExistsError:
            return False
        with os.fdopen(fd, 'w') as f:
            f.write(f'{socket.gethostname()} {slurm_job_id()}\n')
        return True

    def release(self, key):
        os.remove(self._marker(key, '.lock'))

    def mark_done(self, key, info):
        with atomic_write(self._marker(key, '.done')) as f:
            f.write(json.dumps(info) + '\n')

    def local_warc(self, key):
        return os.path.join(self.path, os.path.basename(key))

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
    """Yield one row per (article link, pattern) where the pattern is a substring of the href."""
    for path in paths:
        with open(path, encoding='utf-8') as f:
            for line in f:
                if not any(p in line for p in patterns):  # skip the json parse for most lines
                    continue
                article = json.loads(line)
                for link in article['links']:
                    for pattern in (p for p in patterns if p in link['href']):
                        yield {'pattern': pattern, 'href': link['href'], 'link_text': link['text'],
                               'url': article['url'], 'title': article['title'],
                               'language': article['language'], 'links_file': os.path.basename(path)}


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


def with_max_n(name, max_n):
    """'a' -> 'a.max100' and 'a.jsonl' -> 'a.max100.jsonl' for test runs; unchanged when max_n is None."""
    if not max_n:
        return name
    stem, ext = os.path.splitext(name)
    return f'{stem}.max{max_n}{ext}'


def slurm_job_id():
    return os.environ.get('SLURM_JOB_ID', f'pid{os.getpid()}')


# ---------------------------------------------------------------- the pipeline

class SeedLinkPipeline:
    """Runs every step for a date range; see the module docstring."""

    def __init__(self, index, extractor, work_dir, output_dir, patterns, matches_path, max_warcs=None):
        self.index = index
        self.extractor = extractor
        self.work_dir = work_dir
        self.output_dir = output_dir
        self.patterns = patterns
        self.matches_path = matches_path
        self.max_warcs = max_warcs
        os.makedirs(output_dir, exist_ok=True)

    def run(self, start_date, end_date):
        keys = self.list_warcs(start_date, end_date)
        self.extract_article_links(keys)
        self.grep_seed_patterns(keys)

    def list_warcs(self, start_date, end_date):
        keys = self.index.list_warcs(start_date, end_date)
        if not keys:
            raise ValueError(f'no CC-NEWS WARCs between {start_date} and {end_date}')
        n_todo = sum(not self.work_dir.is_done(key) for key in keys)
        logger.info('%d WARCs between %s and %s; %d not done yet', len(keys), start_date, end_date, n_todo)
        return keys

    def extract_article_links(self, keys):
        """Process each WARC that is not done and not claimed by another worker, in random order."""
        todo = [key for key in keys if not self.work_dir.is_done(key)]
        random.shuffle(todo)
        n_processed = 0
        for key in todo:
            if self.work_dir.is_done(key) or not self.work_dir.claim(key):
                continue
            try:
                self.process_warc(key)
            finally:
                self.work_dir.release(key)  # also on failure, so a rerun can pick the WARC up
            n_processed += 1
            if self.max_warcs and n_processed >= self.max_warcs:
                break
        logger.info('this worker processed %d WARCs', n_processed)

    def process_warc(self, key):
        """Download one WARC, write its links jsonl, mark it done, delete it."""
        local_warc = self.work_dir.local_warc(key)
        if not os.path.exists(local_warc):
            self.index.download(key, local_warc)

        out_path = self.links_path(key)
        with open_with_progress(local_warc) as stream:
            write_jsonl(out_path, self.extractor.rows(stream))

        counts = dict(self.extractor.counts)
        self.work_dir.mark_done(key, {'warc': key, 'output': out_path, **counts,
                                      'finished_at': datetime.datetime.now().isoformat(),
                                      'host': socket.gethostname(), 'slurm_job_id': slurm_job_id()})
        os.remove(local_warc)
        logger.info('done %s %s', warc_name(key), counts)

    def grep_seed_patterns(self, keys):
        """Write the matches, but only once every WARC is done (the last worker to finish does it)."""
        n_not_done = sum(not self.work_dir.is_done(key) for key in keys)
        if n_not_done:
            logger.info('%d WARCs not done yet (other workers, or -max-warcs); not grepping', n_not_done)
            return

        paths = [self.links_path(key) for key in keys]
        matches = list(grep_links(paths, self.patterns))
        os.makedirs(os.path.dirname(self.matches_path), exist_ok=True)
        write_jsonl(self.matches_path, matches)

        counts = Counter(match['pattern'] for match in matches)
        print(f'Grepped {len(paths)} links files -> {self.matches_path}')
        for pattern in self.patterns:
            print(f'  {counts[pattern]:6d}  {pattern}')
        print('\nSpot checks:')
        print(f'  ls {self.work_dir.path}/*.done | wc -l   # should be {len(keys)}')
        print(f"  cat {self.work_dir.path}/*.done | jq -s 'map(.rows) | add'")
        print(f'  jq -r .pattern {self.matches_path} | sort | uniq -c')
        print(f"  jq -c '{{href, url, language}}' {self.matches_path} | head")

    def links_path(self, key):
        return os.path.join(self.output_dir, with_max_n(warc_name(key), self.work_dir.max_n) + '.jsonl')


# ---------------------------------------------------------------- command line

def parse_args():
    """SLURM passes unset optional values as '', so every optional flag treats '' as its default."""
    parser = argparse.ArgumentParser(description='Find which CC-NEWS articles link to a set of seed URLs')
    parser.add_argument('-start-date', required=True, type=parse_date, help='YYYYMMDD, inclusive')
    parser.add_argument('-end-date', required=True, type=parse_date, help='YYYYMMDD, inclusive')
    parser.add_argument('-aws', default='aws', help='path to the aws CLI')
    parser.add_argument('-work-dir', default='', help='downloads and .lock/.done files (default $TMP/find_seed_links)')
    parser.add_argument('-output-dir', default='', help=f'links jsonl files (default {DEFAULT_OUTPUT_DIR})')
    parser.add_argument('-patterns', default=DEFAULT_PATTERNS, help='one substring per line')
    parser.add_argument('-matches-path', default='', help=f'default {DEFAULT_MATCHES_PATH}')
    parser.add_argument('-max-n', type=optional_int, default=None, help='stop after N rows per WARC (testing)')
    parser.add_argument('-max-warcs', type=optional_int, default=None, help='stop after N WARCs (testing)')
    return parser.parse_args()


def parse_date(text):
    return datetime.datetime.strptime(text, '%Y%m%d').date()


def optional_int(text):
    return int(text) if text else None


def default_work_dir():
    if not os.environ.get('TMP'):
        raise EnvironmentError('$TMP is not set; set it or pass -work-dir')
    return os.path.join(os.environ['TMP'], 'find_seed_links')


def main():
    args = parse_args()
    logging.basicConfig(level=logging.INFO)
    logging.getLogger('readability').setLevel(logging.ERROR)  # noisy on malformed pages
    pipeline = SeedLinkPipeline(
        index=CCNewsIndex(args.aws),
        extractor=ArticleLinkExtractor(max_n=args.max_n),
        work_dir=WorkDir(args.work_dir or default_work_dir(), args.max_n),
        output_dir=args.output_dir or DEFAULT_OUTPUT_DIR,
        patterns=read_patterns(args.patterns),
        matches_path=args.matches_path or with_max_n(DEFAULT_MATCHES_PATH, args.max_n),
        max_warcs=args.max_warcs,
    )
    pipeline.run(args.start_date, args.end_date)


if __name__ == '__main__':
    main()
