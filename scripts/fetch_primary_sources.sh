#!/bin/bash
# Fetch the raw text of the URLs on the primary-source store's to-do list (data/interim/primary/todo.tsv; add to it
# with scripts/add_primary_todo.py) with N_WORKERS workers -> data/interim/primary/<sha1>.json. URLs already
# fetched are skipped, so rerun after adding to the list.
#
# Usage (from the repo root):
#   bash scripts/fetch_primary_sources.sh
#   N_WORKERS=1 MAX_FILES=5 bash scripts/fetch_primary_sources.sh         # test

set -eo pipefail  # no -u: ~/.myrc references unset vars
source ~/.myrc
mkdir -p logs/scripts/slurm
N_WORKERS=${N_WORKERS:-50}
for ((i = 0; i < N_WORKERS; i++)); do
    sbatch --parsable --export="MAX_FILES=$MAX_FILES" \
        scripts/slurm/fetch_primary_sources.slurm > /dev/null
    sleep 0.5
done
echo "fetch_primary_sources: $N_WORKERS workers"
echo
echo "Spot checks:"
echo "  ls data/interim/primary | grep -c json                   # sources fetched"
echo "  grep -h 'done ' logs/scripts/slurm/fetch_primary_sources_*.out | tail"
echo "  find data/interim/primary -name '*.json' | xargs cat | jq -r .status | sort | uniq -c   # 200 vs failures (0: error)"
