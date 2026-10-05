#!/bin/bash
# Fetch the raw text of the primary sources (data/processed/primary_sources.tsv) with N_WORKERS workers
# -> data/interim/primary/<sha1>.json. Sources already fetched are skipped, so rerun when the TSV grows.
#
# Usage (from the repo root):
#   bash scripts/fetch_primary_sources.sh
#   MIN_OUTLETS=10 N_WORKERS=50 bash scripts/fetch_primary_sources.sh     # only sources linked by 10+ outlets
#   N_WORKERS=1 MAX_FILES=5 bash scripts/fetch_primary_sources.sh         # test

set -eo pipefail  # no -u: ~/.myrc references unset vars
source ~/.myrc
mkdir -p logs/scripts/slurm
N_WORKERS=${N_WORKERS:-50}
for ((i = 0; i < N_WORKERS; i++)); do
    sbatch --parsable --export="MIN_OUTLETS=${MIN_OUTLETS:-0},MAX_FILES=$MAX_FILES" \
        scripts/slurm/fetch_primary_sources.slurm > /dev/null
    sleep 0.5
done
echo "fetch_primary_sources: $N_WORKERS workers"
echo
echo "Spot checks:"
echo "  ls data/interim/primary | grep -c json                   # sources fetched"
echo "  grep -h 'done ' logs/scripts/slurm/fetch_primary_sources_*.out | tail"
echo "  cat data/interim/primary/*.json | jq -r .status | sort | uniq -c     # 200 vs failures (0: error)"
