#!/bin/bash
# Driver for the whole pipeline: submits it to SLURM and returns right away.
#   update_env       create the translation conda env and pip install config/requirements.txt
#   find_seed_links    N_WORKERS copies of scripts/find_seed_links.py, after update_env succeeds. Each
#                      lists the WARCs, processes the ones not done or claimed, and the last one to
#                      finish greps the links for config/seed_patterns.txt.
#   extract_warc_html  N_HTML_WORKERS copies of scripts/extract_warc_html.py, also after update_env:
#                      raw en/zh article HTML -> data/interim/cc_html/<warc>.parquet. Has its own
#                      .lock/.done files, so it never skips or blocks find_seed_links. 0 = skip it.
#   report_run_done  after every worker ends: prints a summary and sends the one "done" email.
#                    Workers and update_env only email on failure.
# Safe to rerun: done WARCs are skipped, and downloaded WARCs are cached in $TMP/cc_news_warcs. Clean slate: bash scripts/flush.sh
# Logs: logs/scripts/slurm/<job>_<id>.out. Run from the repo root.
#
# Usage:
#   START_DATE=20260901 END_DATE=20260923 bash scripts/go.sh
#   START_DATE=20260901 END_DATE=20260923 N_WORKERS=20 N_HTML_WORKERS=20 bash scripts/go.sh
#   START_DATE=20260901 END_DATE=20260923 N_WORKERS=0 bash scripts/go.sh   # HTML only
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
N_HTML_WORKERS=${N_HTML_WORKERS:-10}
AWS=/home/abha4861/bin/v2/2.5.4/bin/aws  # aws CLI v2 on Alpine (an alias there, so not on PATH in jobs)
mkdir -p logs/scripts/slurm  # SLURM won't create the --output dir

# --export=NONE: without it sbatch copies this shell's environment (--export=ALL), including the
# login node's MODULEPATH, and `module load anaconda` then fails on the compute node.
ENV_JOB=$(sbatch --parsable --export=NONE scripts/slurm/update_env.slurm)
echo "update_env       $ENV_JOB"

# Passed to every worker. Unset optional vars go through empty, and the worker ignores them.
EXPORTS="START_DATE=$START_DATE,END_DATE=$END_DATE,AWS=$AWS,TMP=$TMP,MAX_N=$MAX_N,MAX_WARCS=$MAX_WARCS"
WORKER_JOBS=""
submit_workers() {  # submit_workers <slurm script> <how many>
    for ((i = 0; i < $2; i++)); do
        JOB=$(sbatch --parsable --dependency=afterok:"$ENV_JOB" --kill-on-invalid-dep=yes \
            --export="$EXPORTS" "$1")
        WORKER_JOBS+=":$JOB"
    done
    echo "$(basename "$1" .slurm)  $2 workers (after $ENV_JOB)"
}
submit_workers scripts/slurm/find_seed_links.slurm "$N_WORKERS"
submit_workers scripts/slurm/extract_warc_html.slurm "$N_HTML_WORKERS"
if [ -z "$WORKER_JOBS" ]; then
    echo "No workers submitted (N_WORKERS=0 and N_HTML_WORKERS=0)"
    exit 0
fi

REPORT_JOB=$(sbatch --parsable --dependency=afterany"$WORKER_JOBS" --export="TMP=$TMP" \
    scripts/slurm/report_run_done.slurm)
echo "report_run_done  $REPORT_JOB (after all workers end)"

echo
echo "Spot checks:"
echo "  squeue -u \$USER --name=update_env,find_seed_links,extract_warc_html,report_run_done"
echo "  ls $TMP/find_seed_links/*.done $TMP/extract_warc_html/*.done | wc -l   # WARCs finished (both)"
echo "  ls $TMP/*/*.lock                          # in progress (stale if no job is running)"
echo "  du -sh $TMP/cc_news_warcs                 # WARC cache, shared by both steps and kept"
echo "  tail logs/scripts/slurm/{find_seed_links,extract_warc_html}_*.out"
