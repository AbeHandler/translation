"""
Finding stories that name gazetteer entries among their named entities (the NER files of src/ner_html.py).
Logic only: no paths.

A gazetteer (YAML) maps a canonical name to the ways it is written. An entity matches an entry when the entity's
text contains one of those forms as a whole word, ignoring case. Only the NER entities are searched, not the
raw text, so a match is always something spaCy recognized as a name.
"""
import json
import os
import re

import pyarrow.parquet as pq
import yaml

READ_ROWS = 500  # pages read at a time


def read_gazetteer(path):
    """{canonical: [forms]}. Raises on an empty file, an entry without forms, or a form under two names."""
    with open(path, encoding='utf-8') as f:
        entries = yaml.safe_load(f) or {}
    if not entries:
        raise ValueError(f'no entries in {path}')
    owner = {}
    for canonical, forms in entries.items():
        if not forms or not all(isinstance(form, str) and form.strip() for form in forms):
            raise ValueError(f'{path}: {canonical!r} needs a list of forms, e.g. {canonical}: [{canonical}]')
        for form in forms:
            if form.casefold() in owner and owner[form.casefold()] != canonical:
                raise ValueError(f'{path}: {form!r} is listed under both {owner[form.casefold()]!r} and {canonical!r}')
            owner[form.casefold()] = canonical
    return {str(canonical): [str(form) for form in forms] for canonical, forms in entries.items()}


class Gazetteer:
    def __init__(self, entries):
        # longest forms first, so "Dario Amodei" is reported as the surface form rather than "Amodei"
        self.patterns = {canonical: re.compile('|'.join(rf'(?<!\w){re.escape(form)}(?!\w)'
                                                        for form in sorted(forms, key=len, reverse=True)), re.I)
                         for canonical, forms in entries.items()}

    def matches(self, entities):
        """[{canonical, form, entity, ner_label, start_char, end_char}] for the entities naming an entry."""
        found = []
        for entity in entities or []:
            for canonical, pattern in self.patterns.items():
                hit = pattern.search(entity['text'])
                if hit:
                    found.append({'canonical': canonical, 'form': hit.group(0), 'entity': entity['text'],
                                  'ner_label': entity['label'], 'start_char': entity['start_char'],
                                  'end_char': entity['end_char']})
        return found


def stories(ner_path, html_path, gazetteer, source='cc_news'):
    """Yield a story per page of a NER file that names a gazetteer entry: its text, where it came from, and
    its matches. warc_date comes from the page's HTML file, which has the same rows in the same order."""
    warc = os.path.basename(ner_path).removesuffix('.parquet')
    html = pq.read_table(html_path, columns=['record_id', 'warc_date']).to_pydict()
    row = 0
    parquet = pq.ParquetFile(ner_path)
    columns = ['record_id', 'url', 'language', 'text', 'entities']
    for batch in parquet.iter_batches(batch_size=READ_ROWS, columns=columns):
        for page in batch.to_pylist():
            if html['record_id'][row] != page['record_id']:
                raise ValueError(f'{ner_path} and {html_path} have different rows at {row}; rerun the ner step')
            matches = gazetteer.matches(page['entities'])
            if matches:
                yield {'record_id': page['record_id'], 'url': page['url'], 'source': source, 'warc': warc,
                       'language': page['language'], 'warc_date': html['warc_date'][row],
                       'title': page['text'].split('\n', 1)[0], 'text': page['text'], 'matches': matches,
                       'canonicals': sorted({match['canonical'] for match in matches})}
            row += 1


def write_stories(pairs, gazetteer, out_path):
    """Write the stories of every (ner_path, html_path) to out_path (JSONL, via .part so a partial file never
    looks done). Returns {canonical: number of stories naming it} and the number of stories."""
    counts, n_stories = {}, 0
    os.makedirs(os.path.dirname(os.path.abspath(out_path)), exist_ok=True)
    with open(out_path + '.part', 'w', encoding='utf-8') as f:
        for ner_path, html_path in pairs:
            for story in stories(ner_path, html_path, gazetteer):
                f.write(json.dumps(story, ensure_ascii=False) + '\n')
                n_stories += 1
                for canonical in story['canonicals']:
                    counts[canonical] = counts.get(canonical, 0) + 1
    os.rename(out_path + '.part', out_path)
    return counts, n_stories
