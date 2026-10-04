"""
Is an English screenshot by (or quoting) a notable account? Notable accounts are Wikidata items with an X/Twitter
username (P2002): ~465K people and organizations, each with its number of Wikipedia language editions (sitelinks,
a notability score: 0 = no article, 200 = Elon Musk), plus a hand-made list of ones Wikidata lacks. A screenshot's
OCR text is matched by @handle (OCR may garble the text around it: "Q@ShunyuYao14", "@ @reidhoffman") and, as a
backup when the handle is unreadable, by a notable person's name of 2+ words. Logic only.
"""
import csv
import re

# Wikidata (QLever's endpoint answers it in ~20 s): every item with an X username, its English name, Wikipedia count,
# and whether it is a person.
WIKIDATA_QUERY = """
PREFIX wdt: <http://www.wikidata.org/prop/direct/>
PREFIX wikibase: <http://wikiba.se/ontology#>
PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
PREFIX wd: <http://www.wikidata.org/entity/>
SELECT ?item ?handle ?name ?sitelinks ?human WHERE {
  ?item wdt:P2002 ?handle .
  OPTIONAL { ?item wikibase:sitelinks ?sitelinks }
  OPTIONAL { ?item rdfs:label ?name . FILTER(LANG(?name) = "en") }
  BIND(EXISTS { ?item wdt:P31 wd:Q5 } AS ?human)
}
"""
COLUMNS = ['handle', 'name', 'sitelinks', 'human', 'qid']
MIN_SITELINKS = 1        # notable: has a Wikipedia article in at least one language
HANDLE = re.compile(r'@\s?([A-Za-z0-9_]{2,15})')
NAME_TOKEN = re.compile(r"[^\W\d_]+(?:['-][^\W\d_]+)*")


def parse_wikidata_tsv(text):
    """QLever's TSV answer -> rows {handle, name, sitelinks, human, qid}."""
    lines = text.splitlines()
    for line in lines[1:]:
        item, handle, name, sitelinks, human = (line.split('\t') + [''] * 5)[:5]
        yield {'handle': handle.strip('"'), 'name': re.sub(r'^"(.*)"@en$', r'\1', name),
               'sitelinks': int(sitelinks or 0), 'human': human == 'true',
               'qid': item.rsplit('/', 1)[-1].rstrip('>')}


def name_key(text):
    return ' '.join(t.lower() for t in NAME_TOKEN.findall(text))


class NotableAccounts:
    def __init__(self, rows, min_sitelinks=MIN_SITELINKS):
        self.by_handle, self.by_name = {}, {}
        for row in rows:
            if row['sitelinks'] < min_sitelinks:
                continue
            handle = row['handle'].lower()
            if row['sitelinks'] > self.by_handle.get(handle, {'sitelinks': -1})['sitelinks']:
                self.by_handle[handle] = row
            key = name_key(row['name'])
            if row['human'] and len(key.split()) >= 2 and \
                    row['sitelinks'] > self.by_name.get(key, {'sitelinks': -1})['sitelinks']:
                self.by_name[key] = row
        self.longest_name = max((len(k.split()) for k in self.by_name), default=0)

    @classmethod
    def from_files(cls, *paths, **kwargs):
        rows = []
        for path in paths:
            with open(path, encoding='utf-8', newline='') as f:
                rows += [{**r, 'sitelinks': int(r['sitelinks'] or 0), 'human': r['human'] == 'true'}
                         for r in csv.DictReader(f, delimiter='\t')]
        return cls(rows, **kwargs)

    def match(self, text):
        """[{handle, name, sitelinks, human, qid, how}] of the notable accounts in the text, by @handle first, then
        by a person's name; each account once, in order of appearance."""
        found, seen = [], set()
        for handle in HANDLE.findall(text):
            row = self.by_handle.get(handle.lower())
            if row and row['qid'] + row['handle'] not in seen:
                seen.add(row['qid'] + row['handle'])
                found.append({**row, 'how': 'handle'})
        qids = {r['qid'] for r in found}
        tokens = name_key(text).split()
        for n in range(self.longest_name, 1, -1):
            for i in range(len(tokens) - n + 1):
                row = self.by_name.get(' '.join(tokens[i:i + n]))
                if row and row['qid'] not in qids:
                    qids.add(row['qid'])
                    found.append({**row, 'how': 'name'})
        return found
