#!/bin/bash
# The regular Common Crawl since 2023, streamed once, keeping English pages that say "AI" -> $TMP/cc_full/
# (scripts/cc_full.py). One worker: a single job that writes the WARC list (if it isn't there yet), then works
# through it in random order. N_WORKERS > 1: a list job, then N filter workers reading that list. Every worker
# skips WARCs done or claimed, so rerun or add workers any time. ~3.6M WARCs: whatever gets done is a random
# sample. Run from the repo root.
#
# `links`: N_WORKERS (default 50) link workers (each .ai.warc.gz -> .links.jsonl), then a queue job writing one
# shard per links file to $TMP/cc_full_queue (then: bash scripts/process_queue.sh cc_full), and a cleanup job
# emptying the AI WARCs that have links files (the empty file keeps them marked done). KEEP_WARCS=1: no cleanup.
# Rerun it whenever more WARCs are done: only new ones get links and shards.
#
# Usage:
#   bash scripts/go_cc_full.sh                     # one worker
#   N_WORKERS=100 bash scripts/go_cc_full.sh
#   N_WORKERS=1 MAX_WARCS=1 bash scripts/go_cc_full.sh   # test: one WARC
#   bash scripts/go_cc_full.sh links               # links of the AI pages streamed so far, then the queue + cleanup

set -eo pipefail  # no -u: ~/.myrc references unset vars
source ~/.myrc

if [ -z "${TMP:-}" ]; then
    echo "ERROR: \$TMP is not set (in ~/.myrc); the output goes in \$TMP/cc_full"
    exit 1
fi
if [ "${1:-}" = links ]; then N_WORKERS=${N_WORKERS:-50}; else N_WORKERS=${N_WORKERS:-1}; fi
mkdir -p logs/scripts/slurm
EXPORTS="SINCE_YEAR=$SINCE_YEAR,MAX_WARCS=$MAX_WARCS"

ENV_JOB=$(sbatch --parsable --export=NONE scripts/slurm/update_env.slurm)
echo "update_env      $ENV_JOB"
if [ "${1:-}" = links ]; then
    JOBS=""
    for ((i = 0; i < N_WORKERS; i++)); do
        JOBS+=":$(sbatch --parsable --job-name=cc_full_links --dependency=afterok:"$ENV_JOB" --kill-on-invalid-dep=yes \
            --export="STEP=links,$EXPORTS" scripts/slurm/cc_full.slurm)"
    done
    QUEUE_JOB=$(sbatch --parsable --job-name=cc_full_queue --dependency=afterany"$JOBS" \
        --export="STEP=queue,$EXPORTS" scripts/slurm/cc_full.slurm)
    echo "cc_full_links   $N_WORKERS workers, then cc_full_queue $QUEUE_JOB"
    if [ "${KEEP_WARCS:-}" != 1 ]; then
        CLEANUP_JOB=$(sbatch --parsable --job-name=cc_full_cleanup --dependency=afterany"$JOBS" \
            --export="STEP=cleanup,$EXPORTS" scripts/slurm/cc_full.slurm)
        echo "cc_full_cleanup $CLEANUP_JOB (empties AI WARCs that have links files)"
    fi
    echo "  then: bash scripts/process_queue.sh cc_full"
    exit 0
fi
if [ "$N_WORKERS" -eq 1 ]; then
    JOB=$(sbatch --parsable --job-name=cc_full_all --dependency=afterok:"$ENV_JOB" --kill-on-invalid-dep=yes \
        --export="STEP=all,$EXPORTS" scripts/slurm/cc_full.slurm)
    echo "cc_full_all     $JOB (list, then filter)"
else
    LIST_JOB=$(sbatch --parsable --job-name=cc_full_list --dependency=afterok:"$ENV_JOB" --kill-on-invalid-dep=yes \
        --export="STEP=list,$EXPORTS" scripts/slurm/cc_full.slurm)
    for ((i = 0; i < N_WORKERS; i++)); do
        sbatch --parsable --job-name=cc_full_filter --dependency=afterok:"$LIST_JOB" --kill-on-invalid-dep=yes \
            --export="STEP=filter,$EXPORTS" scripts/slurm/cc_full.slurm > /dev/null
    done
    echo "cc_full_list    $LIST_JOB, then $N_WORKERS cc_full_filter workers"
fi
echo
echo "Spot checks:"
echo "  squeue -u \$USER --name=cc_full_all,cc_full_list,cc_full_filter | wc -l"
echo "  wc -l \$TMP/cc_full/warc_paths.txt                   # WARCs listed"
echo "  ls \$TMP/cc_full/*.ai.warc.gz | wc -l                # WARCs done"
echo "  grep -h '^INFO.*done' logs/scripts/slurm/cc_full_*.out | tail -3   # kept per WARC"
