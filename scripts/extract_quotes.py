#!/usr/bin/env python
"""
Run the direct-quote extractor (src/quote_extraction) over gazetteer stories (scripts/filter_by_gazetteer.py) and
write one line per quotation found: the story's url/title/date, the quote, its type and speaker, the paragraph it
is in, and which gazetteer entries that paragraph names (so quotes near e.g. DeepSeek are easy to pull out).

Run as a module from the repo root:
    python -m scripts.extract_quotes -stories /tmp/gazetteer_stories.jsonl -out /tmp/quotes.jsonl \
        -model-dir results/train_quote_extractor/electra_small/model -only DeepSeek "Moonshot AI" MiniMax
"""
import argparse
import json
import re
import time

from src.quote_extraction.predict import QuoteExtractor

PARAGRAPH = re.compile(r'[^\n]+(?:\n(?!\s*\n)[^\n]+)*')


def parse_args():
    parser = argparse.ArgumentParser(description='Direct quotes in gazetteer stories')
    parser.add_argument('-stories', required=True, help='gazetteer_stories.jsonl')
    parser.add_argument('-out', required=True)
    parser.add_argument('-model-dir', required=True)
    parser.add_argument('-only', nargs='*', default=[], help='only stories naming one of these gazetteer entries')
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
               'record_id': story['record_id'], **quote,
               'paragraph_canonicals': sorted({m['canonical'] for m in story['matches']
                                               if p_start <= m['start_char'] < p_end}),
               'paragraph': story['text'][p_start:p_end]}


def main():
    args = parse_args()
    extractor = QuoteExtractor(args.model_dir)
    wanted = set(args.only)
    n_stories = n_quotes = 0
    started = time.time()
    with open(args.stories, encoding='utf-8') as f, open(args.out, 'w', encoding='utf-8') as out:
        for line in f:
            story = json.loads(line)
            if wanted and not wanted & set(story['canonicals']):
                continue
            n_stories += 1
            for row in quote_rows(story, extractor):
                out.write(json.dumps(row, ensure_ascii=False) + '\n')
                n_quotes += 1
            if n_stories % 50 == 0:
                print(f'{n_stories} stories, {n_quotes} quotes ({time.time() - started:.0f}s)', flush=True)
    print(f'{n_stories} stories, {n_quotes} quotes -> {args.out}')


if __name__ == '__main__':
    main()
