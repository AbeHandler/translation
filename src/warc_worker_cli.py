"""Command-line pieces shared by the WARC worker scripts (scripts/find_seed_links.py,
scripts/extract_warc_html.py), so each script only adds its own flags."""
import datetime
import logging
import signal
import sys


def add_warc_worker_args(parser, default_work_dir_help):
    """Flags every WARC worker takes. SLURM passes unset optional values as '', so '' means default."""
    parser.add_argument('-start-date', required=True, type=parse_date, help='YYYYMMDD, inclusive')
    parser.add_argument('-end-date', required=True, type=parse_date, help='YYYYMMDD, inclusive')
    parser.add_argument('-aws', default='aws', help='path to the aws CLI')
    parser.add_argument('-work-dir', default='', help=f'downloads and .lock/.done files ({default_work_dir_help})')
    parser.add_argument('-max-n', type=optional_int, default=None, help='stop after N rows per WARC (testing)')
    parser.add_argument('-max-warcs', type=optional_int, default=None, help='stop after N WARCs (testing)')


def parse_date(text):
    return datetime.datetime.strptime(text, '%Y%m%d').date()


def optional_int(text):
    return int(text) if text else None


def setup_worker_process():
    """Logging, plus a clean exit on SIGTERM (scancel, SLURM time limit): exiting normally runs the
    worker's `finally`, which removes its .lock so no WARC gets stuck."""
    signal.signal(signal.SIGTERM, lambda signum, frame: sys.exit(f'got signal {signum}; exiting'))
    logging.basicConfig(level=logging.INFO)
    logging.getLogger('readability').setLevel(logging.ERROR)  # noisy on malformed pages
