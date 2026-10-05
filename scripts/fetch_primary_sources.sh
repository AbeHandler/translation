#!/bin/bash
# The primary-source store, in one go: add the primary sources (data/processed/primary_sources.tsv, linked by
# MIN_OUTLETS+ outlets) to the to-do list (scripts/slurm/add_primary_todo.slurm), then N_WORKERS workers fetch
# everything on the list without a file yet -> data/interim/primary/<sha1>.json, then the store is compiled into
# data/processed/primary.pq (scripts/slurm/compile_primary_sources.slurm, emails when done). Rerun any time: URLs
# already listed
# or fetched are skipped. Other URL lists: sbatch --export=TSV=...,COLUMN=... scripts/slurm/add_primary_todo.slurm
#
# Usage (from the repo root):
#   bash scripts/fetch_primary_sources.sh
#   MIN_OUTLETS=5 bash scripts/fetch_primary_sources.sh                  # only sources linked by 5+ outlets
#   N_WORKERS=1 MAX_FILES=5 bash scripts/fetch_primary_sources.sh         # test

set -eo pipefail  # no -u: ~/.myrc references unset vars
source ~/.myrc
mkdir -p logs/scripts/slurm
N_WORKERS=${N_WORKERS:-50}
TODO=$(sbatch --parsable --export="MIN_OUTLETS=${MIN_OUTLETS:-0}" scripts/slurm/add_primary_todo.slurm)
echo "add_primary_todo $TODO"
ids=""
for ((i = 0; i < N_WORKERS; i++)); do
    ids+=":$(sbatch --parsable --dependency=afterok:$TODO --export="MAX_FILES=$MAX_FILES" \
        scripts/slurm/fetch_primary_sources.slurm)"
    sleep 0.5
done
COMPILE=$(sbatch --parsable --dependency="afterany$ids" --export=NONE scripts/slurm/compile_primary_sources.slurm)
echo "fetch_primary_sources: $N_WORKERS workers, after $TODO; then compile_primary_sources $COMPILE -> primary.pq"
echo
echo "Spot checks:"
echo "  tail -2 logs/scripts/slurm/add_primary_todo_$TODO.out          # URLs added to the list"
echo "  ls -f data/interim/primary | grep -c json$                  # sources fetched"
echo "  grep -h 'done ' logs/scripts/slurm/fetch_primary_sources_*.out | tail"
echo "  find data/interim/primary -name '*.json' | xargs cat | jq -r .status | sort | uniq -c   # 200 vs failures (0: error)"
