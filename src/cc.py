#!/usr/bin/env python
"""
Find the links in each article of CC-NEWS WARC files for a date range.

CCLinkExtractor loops over the HTML responses in a WARC, keeps articles in the wanted languages
(language from news-please), uses readability to keep only the article body (no nav/footer/
sidebars), and yields one row per page:
    {url, title, language, n_links, links: [{href, text, internal}]}

CCNewsIndex lists the WARCs for a date range and downloads them with the aws CLI
(s3://commoncrawl; needs AWS credentials).

Steps (scripts/cc_go.sh submits todo, the workers, then grep, as SLURM jobs):
    todo  write <work-dir>/todo.txt: WARCs in the date range that don't have a .done file yet
    work  shuffle todo.txt and, for each WARC not done or locked by another worker, download it
          to -work-dir, write the links jsonl to -output-dir, write <work-dir>/<warc>.done, and
          delete the WARC. Workers coordinate through the .lock/.done files, so -work-dir must
          be on a shared filesystem.
    grep  scan the links jsonl in -output-dir for the substrings in -patterns and write one row
          per matching link to -matches-path

Usage:
    python src/cc.py -step todo -start-date 20260901 -end-date 20260923
    python src/cc.py -step work
    python src/cc.py -step work -max-warcs 1 -max-n 100
    python src/cc.py -step grep
"""
import argparse
import datetime
import json
import logging
import os
import random
import socket
import subprocess
from types import SimpleNamespace
from urllib.parse import urljoin, urlparse

import lxml.html
from newsplease.pipeline.extractor.extractors.lang_detect_extractor import LangExtractor
from readability import Document
from tqdm import tqdm
from tqdm.utils import CallbackIOWrapper
from warcio.archiveiterator import ArchiveIterator

logger = logging.getLogger(__name__)


class CCLinkExtractor:
    """Extracts article-body links from CC-NEWS WARC files."""

    # news-please two-letter codes (zh covers zh-cn, zh-tw, zh-hk, ...)
    DEFAULT_LANGUAGES = ('en', 'zh')
    SKIP_HREF_PREFIXES = ('#', 'javascript:', 'mailto:', 'tel:')

    def __init__(self, languages=DEFAULT_LANGUAGES, max_n=None):
        self.languages = languages
        self.max_n = max_n
        self.counts = {}
        self._lang_extractor = LangExtractor()

    def iter_rows(self, warc_path):
        """Yield one row per kept article. Progress bar tracks bytes of the .warc.gz read."""
        self.counts = {'rows': 0, 'errors': 0, 'other_language': 0, 'links': 0}
        with open(warc_path, 'rb') as raw, \
                tqdm(total=os.path.getsize(warc_path), unit='B', unit_scale=True, desc='warc',
                     disable=None) as bar:  # no bar in SLURM logs
            stream = CallbackIOWrapper(bar.update, raw, 'read')
            for page_url, html in self._iter_html_responses(stream):
                row = self._to_row(page_url, html)
                if row is None:
                    continue
                self.counts['rows'] += 1
                self.counts['links'] += row['n_links']
                bar.set_postfix(self.counts, refresh=False)
                yield row
                if self.max_n and self.counts['rows'] >= self.max_n:
                    return

    def write_jsonl(self, warc_path, out_path):
        """Write rows to out_path via a .lock file so a partial run never looks finished."""
        lock_path = out_path + '.lock'
        with open(lock_path, 'w', encoding='utf-8') as out:
            for row in self.iter_rows(warc_path):
                out.write(json.dumps(row, ensure_ascii=False) + '\n')
        os.rename(lock_path, out_path)
        return self.counts

    def _to_row(self, page_url, html):
        """Return a row, or None if the page is in another language or can't be parsed."""
        try:
            language = self._get_language(html)
            if language not in self.languages:
                self.counts['other_language'] += 1
                return None
            title, body = self._parse_article(html)
        except Exception as exc:  # empty/garbled pages are common in CC-NEWS
            self.counts['errors'] += 1
            logger.debug('parse failed for %s: %s', page_url, exc)
            return None
        links = self._find_article_links(page_url, body)
        return {'url': page_url, 'title': title, 'language': language, 'n_links': len(links), 'links': links}

    @staticmethod
    def _iter_html_responses(stream):
        """Yield (url, html_bytes) for each HTML response record in an open WARC stream."""
        for record in ArchiveIterator(stream):
            if record.rec_type != 'response':
                continue
            content_type = record.http_headers.get_header('Content-Type') or ''
            if 'html' not in content_type:
                continue
            yield record.rec_headers.get_header('WARC-Target-URI'), record.content_stream().read()

    def _get_language(self, html):
        """
        news-please's article language: <html lang>, then meta tags, then og:locale; langdetect only
        as a last resort. Calls just its language extractor, not the full (slow) news-please pipeline.
        """
        return self._lang_extractor._language({'spider_response': SimpleNamespace(body=html)})

    @staticmethod
    def _parse_article(html):
        """Return (title, body) where body is the lxml tree of the article only (readability)."""
        doc = Document(html)
        return doc.short_title(), lxml.html.fromstring(doc.summary())

    @classmethod
    def _find_article_links(cls, page_url, body):
        """Return links in the article body. Relative hrefs are resolved against page_url."""
        links = []
        for anchor in body.iter('a'):
            href = anchor.get('href', '').strip()
            if not href or href.startswith(cls.SKIP_HREF_PREFIXES):
                continue
            href = urljoin(page_url, href)
            links.append({
                'href': href,
                'text': anchor.text_content().strip(),
                'internal': urlparse(href).netloc == urlparse(page_url).netloc,
            })
        return links


class CCNewsIndex:
    """Lists and downloads CC-NEWS WARC files from s3://commoncrawl with the aws CLI."""

    BUCKET = 's3://commoncrawl/'

    def __init__(self, aws='aws', bucket=BUCKET):
        self.aws = aws
        self.bucket = bucket

    def warc_paths(self, start_date, end_date):
        """Return WARC paths (crawl-data/CC-NEWS/...) crawled on days in [start_date, end_date]."""
        paths = []
        for year, month in self._months(start_date, end_date):
            paths += self._month_paths(year, month)
        return [p for p in paths if start_date <= self.warc_date(p) <= end_date]

    def download(self, warc_path, dest):
        """Download to dest via a .part file, so a killed download never looks complete."""
        part = dest + '.part'
        self._run_aws('s3', 'cp', '--only-show-errors', self.bucket + warc_path, part)
        os.rename(part, dest)

    @staticmethod
    def warc_date(warc_path):
        """CC-NEWS-20260923153007-00006.warc.gz -> date(2026, 9, 23)"""
        stamp = os.path.basename(warc_path).split('-')[2]
        return datetime.datetime.strptime(stamp[:8], '%Y%m%d').date()

    def _month_paths(self, year, month):
        """`aws s3 ls` lines look like: 2026-09-23 16:01:02 1072866466 CC-NEWS-20260923153007-00006.warc.gz"""
        prefix = f'crawl-data/CC-NEWS/{year}/{month:02d}/'
        listing = self._run_aws('s3', 'ls', self.bucket + prefix)
        names = [line.split()[-1] for line in listing.splitlines() if line.endswith('.warc.gz')]
        return [prefix + name for name in names]

    def _run_aws(self, *args):
        """Run the aws CLI and return stdout; raises with aws's stderr on failure."""
        result = subprocess.run([self.aws, *args], capture_output=True, text=True)
        if result.returncode != 0:
            raise RuntimeError(f'{self.aws} {" ".join(args)} failed:\n{result.stderr}')
        return result.stdout

    @staticmethod
    def _months(start_date, end_date):
        year, month = start_date.year, start_date.month
        while (year, month) <= (end_date.year, end_date.month):
            yield year, month
            year, month = (year + 1, 1) if month == 12 else (year, month + 1)


DEFAULT_OUTPUT_DIR = './data/interim/cc_links/'
DEFAULT_MATCHES_PATH = './data/processed/cc_link_matches.jsonl'


def parse_args():
    parser = argparse.ArgumentParser(description="Find the links in each article of CC-NEWS WARCs for a date range")
    parser.add_argument("-step", required=True, choices=['todo', 'work', 'grep'])
    parser.add_argument("-start-date", type=parse_date, help="todo step: YYYYMMDD, inclusive")
    parser.add_argument("-end-date", type=parse_date, help="todo step: YYYYMMDD, inclusive")
    parser.add_argument("-output-dir", default='', help=f"default {DEFAULT_OUTPUT_DIR}")
    parser.add_argument("-patterns", default='config/seed_patterns.txt', help="grep step: one substring per line")
    parser.add_argument("-matches-path", default='', help=f"grep step: default {DEFAULT_MATCHES_PATH}")
    parser.add_argument("-aws", default='aws', help="path to the aws CLI")
    parser.add_argument("-work-dir", default=None, help="downloads and .lock/.done files (default $TMP/warcs)")
    # optional_int: SLURM passes unset options as '', which means no limit
    parser.add_argument("-max-n", type=optional_int, default=None, help="stop after N rows per WARC (testing)")
    parser.add_argument("-max-warcs", type=optional_int, default=None, help="stop after N WARCs (testing)")
    return parser.parse_args()


def optional_int(text):
    return int(text) if text else None


def parse_date(text):
    return datetime.datetime.strptime(text, '%Y%m%d').date()


def default_work_dir():
    if not os.environ.get('TMP'):
        raise EnvironmentError('$TMP is not set; set it or pass -work-dir')
    return os.path.join(os.environ['TMP'], 'warcs')


def is_done(work_dir, rid):
    return os.path.exists(os.path.join(work_dir, f'{rid}.done'))


def write_todo(index, start_date, end_date, work_dir, max_n):
    """Write todo.txt (WARCs in range not done yet) atomically; returns (n_in_range, n_todo)."""
    warc_paths = index.warc_paths(start_date, end_date)
    if not warc_paths:
        raise ValueError(f'no CC-NEWS WARCs between {start_date} and {end_date}')
    todo = [p for p in warc_paths if not is_done(work_dir, run_id(p, max_n))]
    todo_path = os.path.join(work_dir, 'todo.txt')
    with open(todo_path + '.part', 'w') as f:
        f.write(''.join(p + '\n' for p in todo))
    os.rename(todo_path + '.part', todo_path)
    return len(warc_paths), len(todo)


def read_todo(work_dir):
    todo_path = os.path.join(work_dir, 'todo.txt')
    if not os.path.exists(todo_path):
        raise FileNotFoundError(f'{todo_path} missing; run -step todo first (scripts/cc_go.sh does)')
    with open(todo_path) as f:
        return f.read().split()


def claim(lock_path):
    """Atomically create lock_path. Returns False if another worker already holds it."""
    try:
        fd = os.open(lock_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    except FileExistsError:
        return False
    with os.fdopen(fd, 'w') as f:
        f.write(f'{socket.gethostname()} {os.environ.get("SLURM_JOB_ID", os.getpid())}\n')
    return True


def run_id(warc_path, max_n):
    """CC-NEWS-...-00006 (full run) or CC-NEWS-...-00006.max100 (test run), so tests never block real runs."""
    stem = os.path.basename(warc_path).removesuffix('.warc.gz')
    return f'{stem}.max{max_n}' if max_n else stem


def process_warc(warc_path, index, extractor, work_dir, output_dir, max_n):
    """Download one WARC, write its links jsonl, write its .done file, delete the WARC."""
    rid = run_id(warc_path, max_n)
    local_warc = os.path.join(work_dir, os.path.basename(warc_path))
    out_path = os.path.join(output_dir, f'{rid}.jsonl')

    if not os.path.exists(local_warc):
        index.download(warc_path, local_warc)
    counts = extractor.write_jsonl(local_warc, out_path)
    done = {'warc': warc_path, 'output': out_path, 'finished_at': datetime.datetime.now().isoformat(),
            'host': socket.gethostname(), 'slurm_job_id': os.environ.get('SLURM_JOB_ID'), **counts}
    with open(os.path.join(work_dir, f'{rid}.done'), 'w') as f:
        f.write(json.dumps(done) + '\n')
    os.remove(local_warc)
    return counts


def run_worker(warc_paths, index, extractor, work_dir, output_dir, max_n, max_warcs):
    """Loop over the shuffled TODO list, skipping WARCs that are done or locked by another worker."""
    todo = list(warc_paths)
    random.shuffle(todo)
    n_processed = 0
    for warc_path in todo:
        rid = run_id(warc_path, max_n)
        lock_path = os.path.join(work_dir, f'{rid}.lock')
        if is_done(work_dir, rid) or not claim(lock_path):
            continue
        try:
            counts = process_warc(warc_path, index, extractor, work_dir, output_dir, max_n)
        finally:
            os.remove(lock_path)  # on failure, frees the WARC for the next worker/rerun
        n_processed += 1
        logger.info('done %s %s', rid, counts)
        if max_warcs and n_processed >= max_warcs:
            break
    return n_processed


def read_patterns(path):
    """One substring per line; blank lines and # comments are ignored."""
    with open(path) as f:
        patterns = [line.strip() for line in f if line.strip() and not line.startswith('#')]
    if not patterns:
        raise ValueError(f'no patterns in {path}')
    return patterns


def links_files(output_dir, max_n):
    """The links jsonl files for this run type: *.max<N>.jsonl for tests, the rest otherwise."""
    names = sorted(os.listdir(output_dir))
    if max_n:
        return [os.path.join(output_dir, n) for n in names if n.endswith(f'.max{max_n}.jsonl')]
    return [os.path.join(output_dir, n) for n in names if n.endswith('.jsonl') and '.max' not in n]


def grep_links(paths, patterns):
    """Yield one row per (article link, pattern) where the pattern is a substring of the href."""
    for path in paths:
        with open(path, encoding='utf-8') as f:
            for line in f:
                if not any(p in line for p in patterns):  # cheap check before parsing json
                    continue
                article = json.loads(line)
                for link in article['links']:
                    for pattern in patterns:
                        if pattern in link['href']:
                            yield {'pattern': pattern, 'href': link['href'], 'link_text': link['text'],
                                   'url': article['url'], 'title': article['title'],
                                   'language': article['language'], 'links_file': os.path.basename(path)}


def write_matches(paths, patterns, matches_path):
    """Write all matches to matches_path (rebuilt each run, via .part); returns count per pattern."""
    counts = {p: 0 for p in patterns}
    os.makedirs(os.path.dirname(matches_path), exist_ok=True)
    with open(matches_path + '.part', 'w', encoding='utf-8') as out:
        for row in grep_links(paths, patterns):
            out.write(json.dumps(row, ensure_ascii=False) + '\n')
            counts[row['pattern']] += 1
    os.rename(matches_path + '.part', matches_path)
    return counts


def print_spot_checks(work_dir, output_dir, n_todo):
    print('\nSpot checks:')
    print(f'  ls {work_dir}/*.done | wc -l   # of {n_todo} WARCs')
    print(f'  ls {work_dir}/*.lock           # in progress (stale if no job is running)')
    print(f"  cat {work_dir}/*.done | jq -s 'map(.rows) | add'")
    print(f'  cat {output_dir}/*.jsonl | jq -r .language | sort | uniq -c')


def run_grep_step(args, output_dir):
    patterns = read_patterns(args.patterns)
    paths = links_files(output_dir, args.max_n)
    if not paths:
        raise FileNotFoundError(f'no links jsonl files in {output_dir}')
    default_path = DEFAULT_MATCHES_PATH.replace('.jsonl', f'.max{args.max_n}.jsonl') if args.max_n \
        else DEFAULT_MATCHES_PATH
    matches_path = args.matches_path or default_path
    counts = write_matches(paths, patterns, matches_path)
    print(f'Grepped {len(paths)} links files -> {matches_path}')
    for pattern, n in counts.items():
        print(f'  {n:6d}  {pattern}')
    print('\nSpot checks:')
    print(f"  jq -r .pattern {matches_path} | sort | uniq -c")
    print(f"  jq -c '{{href, url, language}}' {matches_path} | head")
    print(f"  jq -r .url {matches_path} | awk -F/ '{{print $3}}' | sort | uniq -c | sort -rn | head")


def main():
    args = parse_args()
    logging.basicConfig(level=logging.INFO)
    logging.getLogger('readability').setLevel(logging.ERROR)  # noisy on malformed pages
    output_dir = args.output_dir or DEFAULT_OUTPUT_DIR
    if args.step == 'grep':
        run_grep_step(args, output_dir)
        return

    work_dir = args.work_dir or default_work_dir()
    os.makedirs(work_dir, exist_ok=True)
    os.makedirs(output_dir, exist_ok=True)

    index = CCNewsIndex(aws=args.aws)
    if args.step == 'todo':
        if not (args.start_date and args.end_date):
            raise ValueError('-step todo needs -start-date and -end-date')
        n_range, n_todo = write_todo(index, args.start_date, args.end_date, work_dir, args.max_n)
        print(f'{n_range} WARCs between {args.start_date} and {args.end_date}; '
              f'{n_todo} still to do -> {work_dir}/todo.txt')
        return

    warc_paths = read_todo(work_dir)
    logger.info('%d WARCs in TODO list', len(warc_paths))
    n = run_worker(warc_paths, index, CCLinkExtractor(max_n=args.max_n), work_dir, output_dir,
                   args.max_n, args.max_warcs)
    print(f'Worker processed {n} WARCs')
    print_spot_checks(work_dir, output_dir, len(warc_paths))


if __name__ == "__main__":
    main()
