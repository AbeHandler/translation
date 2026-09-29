"""
Reading a Wikipedia multistream dump (<lang>wiki-latest-pages-articles-multistream.xml.bz2). The dump is a run of
bz2 streams of ~100 pages each; its index (…-index.txt.bz2, lines "offset:page_id:title") gives each stream's
byte offset. Chunks of streams are the unit of work: each worker reads one byte range, decompresses its
streams and parses the pages, without touching the rest of the file.
"""
import bz2
import os
import re
import subprocess
import xml.etree.ElementTree as ElementTree
from dataclasses import dataclass

DUMP_URL = 'https://dumps.wikimedia.org/{lang}wiki/latest/{lang}wiki-latest-pages-articles-multistream{suffix}'
DUMP_SUFFIX = '.xml.bz2'
INDEX_SUFFIX = '-index.txt.bz2'
NS = '{http://www.mediawiki.org/xml/export-0.11/}'


def dump_paths(dump_dir, lang):
    """(dump, index) local paths."""
    return tuple(os.path.join(dump_dir, f'{lang}wiki-latest-pages-articles-multistream{suffix}')
                 for suffix in (DUMP_SUFFIX, INDEX_SUFFIX))


def download(lang, dump_dir):
    """Download the dump and its index into dump_dir (curl, resuming a partial download). Skips what's there."""
    os.makedirs(dump_dir, exist_ok=True)
    for suffix, path in zip((DUMP_SUFFIX, INDEX_SUFFIX), dump_paths(dump_dir, lang)):
        if os.path.exists(path):
            continue
        subprocess.run(['curl', '--fail', '--silent', '--show-error', '--location', '--retry', '5',
                        '--continue-at', '-', '--output', path + '.part', DUMP_URL.format(lang=lang, suffix=suffix)],
                       check=True)
        os.rename(path + '.part', path)


def stream_offsets(index_path):
    """Sorted byte offsets of the dump's page streams (from the index)."""
    offsets = set()
    with bz2.open(index_path, 'rt', encoding='utf-8') as f:
        for line in f:
            offsets.add(int(line.split(':', 1)[0]))
    return sorted(offsets)


def chunks(offsets, dump_size, streams_per_chunk):
    """[(start, end)] byte ranges of streams_per_chunk streams each; the last one runs to the end of the file."""
    starts = offsets[::streams_per_chunk]
    ends = starts[1:] + [dump_size]
    return list(zip(starts, ends))


@dataclass
class Page:
    page_id: int
    title: str
    ns: int
    redirect: bool
    text: str


PAGE = re.compile(r'<page>.*?</page>', re.S)


def read_pages(dump_path, start, end):
    """Every page in dump bytes [start, end), which must be whole streams."""
    with open(dump_path, 'rb') as f:
        f.seek(start)
        data = f.read(end - start)
    xml = bz2.decompress(data).decode('utf-8')  # handles several concatenated streams
    for match in PAGE.finditer(xml):
        yield parse_page(match.group(0))


def parse_page(page_xml):
    page = ElementTree.fromstring(page_xml)
    return Page(page_id=int(page.findtext('id')), title=page.findtext('title'), ns=int(page.findtext('ns')),
                redirect=page.find('redirect') is not None, text=page.findtext('revision/text') or '')
