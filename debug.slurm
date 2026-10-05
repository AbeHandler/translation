#!/bin/bash
# Debug the Chinese media storms' by_day step (src/media_storms.py split_site_crawl_by_day) on real crawl files:
# one random embedded HTML file from each of up to 12 sites, written to a scratch folder (the real
# data/interim/media_storms_zh is not touched). Prints, per file, its pages by outcome (no embedding, not chinese,
# not about ai, no date, date out of range, kept) and a few kept pages (date, outlet, title).
#
# Usage (from the repo root):
#   sbatch debug.slurm        # then: cat logs/scripts/slurm/debug_<jobid>.out

#SBATCH --partition=acpu
#SBATCH --time=01:00:00
#SBATCH --job-name=debug
#SBATCH --output=logs/scripts/slurm/%x_%j.out
#SBATCH --mem=8G
#SBATCH --qos=cpu-normal
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --mail-type=FAIL
#SBATCH --mail-user=abha4861@colorado.edu

set -eo pipefail  # no -u: ~/.myrc and conda activate reference unset vars
source ~/.myrc

module load anaconda
conda activate translation

OUT=$TMP/debug_media_storms_zh
rm -rf "$OUT"
python - "$OUT" <<'EOF' 2>&1 | grep -v -e UserWarning -e "from . import" -e "INFO:newspaper"
import datetime, glob, json, os, random, sys
from collections import Counter
from src.media_storms import split_site_crawl_by_day
import pyarrow.parquet as pq

out = sys.argv[1]
sites = sorted(glob.glob('data/interim/site_crawls/*/'))
random.shuffle(sites)
total, today = Counter(), datetime.date.today().isoformat()
for site in sites[:12]:
    files = [f for f in glob.glob(site + 'html/*.parquet') if os.path.exists(f.replace('/html/', '/embeddings/'))]
    if not files:
        print(f'{os.path.basename(site[:-1]):24} no embedded HTML files')
        continue
    html = random.choice(files)
    key = os.path.basename(site[:-1]) + '__' + os.path.basename(html)[:-8]
    counts, funnel = split_site_crawl_by_day(html, html.replace('/html/', '/embeddings/'), out + '/days',
                                             f'{out}/{key}.jsonl', key, today)
    total.update(funnel)
    print(f'{os.path.basename(site[:-1]):24} {dict(sorted(funnel.items(), key=lambda kv: -kv[1]))}')
    kept = [(d, r) for d in counts for r in pq.read_table(f'{out}/days/{d}/{key}.parquet', columns=['outlet', 'title']).to_pylist()]
    for d, r in kept[:3]:
        print(f'{"":24}   kept {d} {r["title"][:70]}')
print('\nall files:', dict(sorted(total.items(), key=lambda kv: -kv[1])))
EOF
