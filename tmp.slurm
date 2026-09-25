#!/bin/bash
# Find crawled pages that link to Dario Amodei's essay: every row of data/interim/site_crawls/*/pages.jsonl
# with a link containing PATTERN -> tmp.jsonl (one line per page: domain, url, title, pubdate, pubdate_source,
# crawled_at and the matching links). Safe while the crawls run; it only reads.
#
# Usage (from the repo root):
#   sbatch tmp.slurm

#SBATCH --partition=acpu
#SBATCH --time=01:00:00
#SBATCH --job-name=tmp
#SBATCH --output=logs/scripts/slurm/%x_%j.out
#SBATCH --mem=4G
#SBATCH --qos=cpu-normal
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --mail-type=FAIL
#SBATCH --mail-user=abha4861@colorado.edu

set -eo pipefail  # no -u: ~/.myrc and conda activate reference unset vars
source ~/.myrc

module load anaconda
conda activate translation

PATTERN=darioamodei.com/post/we-must-pace-the-frontier
OUT=tmp.jsonl

# grep -F narrows millions of lines to the few that mention the pattern anywhere; python keeps those where
# it is in a link (not just the title or url) and skips lines a crawl is still writing. grep exiting 1
# just means no matches.
{ grep -hF "$PATTERN" data/interim/site_crawls/*/pages.jsonl || [ $? -eq 1 ]; } | python -c "
import json, sys
from urllib.parse import urlparse
pattern = sys.argv[1]
for line in sys.stdin:
    try:
        page = json.loads(line)
    except json.JSONDecodeError:  # a half-written last line
        continue
    links = [link for link in page['links'] if pattern in link]
    if links:
        row = {'domain': urlparse(page['url']).hostname, **{k: page.get(k) for k in
               ('url', 'title', 'pubdate', 'pubdate_source', 'crawled_at')}, 'matching_links': links}
        print(json.dumps(row, ensure_ascii=False))
" "$PATTERN" > "$OUT.part"
mv "$OUT.part" "$OUT"

echo "Pages linking to $PATTERN: $(wc -l < "$OUT")  -> $OUT"
echo "Per site:"
python -c "
import json, collections
print(collections.Counter(json.loads(l)['domain'] for l in open('$OUT')).most_common())"
echo
echo "Spot checks:"
echo "  head -3 $OUT"
echo "  python -c \"import json; [print(r['pubdate'], r['url'], r['title']) for r in map(json.loads, open('$OUT'))]\""
