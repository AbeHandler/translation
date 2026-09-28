#!/usr/bin/env python
"""
Direct quotes in the gazetteer stories only: runs the quote extractor (src/quote_extraction, trained by
scripts/train_quote_extractor.py) over data/processed/gazetteer_stories.jsonl (scripts/filter_by_gazetteer.py)
-> data/processed/gazetteer_quotes.jsonl, one line per quotation:
    url, title, warc_date, record_id                the story
    quote, quote_type, quote_start, quote_end       quote_type: LeftSpeaker, RightSpeaker or Unknown
    speaker, speaker_start, speaker_end             null when there is none
    n_words                                         to drop short fragments (scare quotes) later
    paragraph, paragraph_canonicals                 the quote's paragraph, and the gazetteer entries it names
Offsets are into the story's text, the same text its entity offsets refer to. Rebuilds the whole file every run.

Run as a module from the repo root:
    python -m scripts.extract_quotes
    python -m scripts.extract_quotes -only DeepSeek "Moonshot AI" MiniMax      # stories naming these only
    python -m scripts.extract_quotes -stories /tmp/gazetteer_stories.jsonl -out /tmp/quotes.jsonl
"""
import argparse
import json
import os
import re
import time

from config.paths import GAZETTEER_QUOTES_PATH, GAZETTEER_STORIES_PATH, QUOTE_MODEL_DIR
from src.cc_news import with_max_n
from src.quote_extraction.predict import QuoteExtractor
from src.warc_worker_cli import optional_int

PARAGRAPH = re.compile(r'[^\n]+(?:\n(?!\s*\n)[^\n]+)*')


def parse_args():
    parser = argparse.ArgumentParser(description='Direct quotes in the gazetteer stories')
    parser.add_argument('-stories', default='', help=f'default {GAZETTEER_STORIES_PATH}')
    parser.add_argument('-out', default='', help=f'default {GAZETTEER_QUOTES_PATH}')
    parser.add_argument('-model-dir', default=str(QUOTE_MODEL_DIR))
    parser.add_argument('-only', nargs='*', default=[], help='only stories naming one of these gazetteer entries')
    parser.add_argument('-max-n', type=optional_int, default=None, help='the .max<N> test files')
    return parser.parse_args()


def paragraph_of(text, start):
    for match in PARAGRAPH.finditer(text):
        if match.start() <= start < match.end():
            return match.start(), match.end()
    return 0, len(text)


def quote_rows(story, extractor):
    for quote in extractor.predict(story['text']):
        p_start, p_end = paragraph_of(story['text'], quote['quote_start'])
        yield {'url': story['url'], 'title': story['title'], 'warc_date': story['warc_date'],
               'record_id': story['record_id'], **quote, 'n_words': len(quote['quote'].split()),
               'paragraph_canonicals': sorted({m['canonical'] for m in story['matches']
                                               if p_start <= m['start_char'] < p_end}),
               'paragraph': story['text'][p_start:p_end]}


def main():
    args = parse_args()
    stories_path = args.stories or with_max_n(str(GAZETTEER_STORIES_PATH), args.max_n)
    out_path = args.out or with_max_n(str(GAZETTEER_QUOTES_PATH), args.max_n)
    if not os.path.isdir(args.model_dir):
        raise FileNotFoundError(f'no quote model at {args.model_dir}; train it with '
                                'scripts/slurm/train_quote_extractor.slurm (or copy it there)')
    extractor = QuoteExtractor(args.model_dir)
    wanted = set(args.only)
    n_stories = n_quotes = 0
    started = time.time()
    with open(stories_path, encoding='utf-8') as f, open(out_path + '.part', 'w', encoding='utf-8') as out:
        for line in f:
            story = json.loads(line)
            if wanted and not wanted & set(story['canonicals']):
                continue
            n_stories += 1
            for row in quote_rows(story, extractor):
                out.write(json.dumps(row, ensure_ascii=False) + '\n')
                n_quotes += 1
            if n_stories % 100 == 0:
                print(f'{n_stories} stories, {n_quotes} quotes ({time.time() - started:.0f}s)', flush=True)
    os.rename(out_path + '.part', out_path)
    print(f'{n_stories} stories, {n_quotes} quotes -> {out_path}')
    print('Spot checks:')
    print(f"  jq -r '.speaker // \"NONE\"' {out_path} | sort | uniq -c | sort -rn | head -30   # who is quoted")
    print(f"  jq -c 'select(.n_words >= 4 and (.paragraph_canonicals | index(\"DeepSeek\"))) | "
          f"{{speaker, quote}}' {out_path} | head")


if __name__ == '__main__':
    main()
