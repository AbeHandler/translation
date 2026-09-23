#!/bin/bash
# Driver for the whole pipeline: submits it to SLURM and returns right away.
#   update_env       create the translation conda env and pip install config/requirements.txt
#   find_seed_links  N_WORKERS copies of scripts/find_seed_links.py, after update_env succeeds. Each lists the
#                    WARCs, processes the ones not done or claimed, and the last one to finish
#                    greps the links for config/seed_patterns.txt.
# Safe to rerun: done WARCs are skipped. Clean slate: bash scripts/flush.sh
# Logs: logs/scripts/slurm/<job>_<id>.out. Run from the repo root.
#
# Usage:
#   START_DATE=20260901 END_DATE=20260923 bash scripts/go.sh
#   START_DATE=20260901 END_DATE=20260923 N_WORKERS=20 bash scripts/go.sh
#   START_DATE=20260923 END_DATE=20260923 N_WORKERS=1 MAX_WARCS=1 MAX_N=100 bash scripts/go.sh  # test

set -eo pipefail  # no -u: ~/.myrc references unset vars
source ~/.myrc  # first, so $TMP etc. from ~/.myrc are set before the checks below

if [ -z "${START_DATE:-}" ] || [ -z "${END_DATE:-}" ]; then
    echo "ERROR: START_DATE and END_DATE (YYYYMMDD) are required"
    echo "Usage: START_DATE=20260901 END_DATE=20260923 bash scripts/go.sh"
    exit 1
fi
if [ -z "${TMP:-}" ]; then
    echo "ERROR: \$TMP is not set; .lock/.done files go in \$TMP/find_seed_links"
    exit 1
fi
N_WORKERS=${N_WORKERS:-10}
AWS=/home/abha4861/bin/v2/2.5.4/bin/aws  # aws CLI v2 on Alpine (an alias there, so not on PATH in jobs)
mkdir -p logs/scripts/slurm  # SLURM won't create the --output dir

ENV_JOB=$(sbatch --parsable scripts/slurm/update_env.slurm)
echo "update_env       $ENV_JOB"

# Passed to every worker. Unset optional vars go through empty, and the worker ignores them.
EXPORTS="START_DATE=$START_DATE,END_DATE=$END_DATE,AWS=$AWS,TMP=$TMP,MAX_N=$MAX_N,MAX_WARCS=$MAX_WARCS"
for i in $(seq 1 "$N_WORKERS"); do
    JOB=$(sbatch --parsable --dependency=afterok:"$ENV_JOB" --kill-on-invalid-dep=yes \
        --export="$EXPORTS" scripts/slurm/find_seed_links.slurm)
    echo "find_seed_links  $JOB (after $ENV_JOB)"
done

echo
echo "Spot checks:"
echo "  squeue -u \$USER --name=update_env,find_seed_links"
echo "  ls $TMP/find_seed_links/*.done | wc -l   # WARCs finished"
echo "  ls $TMP/find_seed_links/*.lock           # in progress (stale if no job is running)"
echo "  tail logs/scripts/slurm/find_seed_links_*.out"
