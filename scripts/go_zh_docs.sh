#!/bin/bash
# One command for the Chinese documents: queue the linked Chinese pages (scripts/slurm/zh_docs_queue.slurm), then
# N_WORKERS fetch workers that wait for it, then the collect job -> data/processed/zh_docs.jsonl
# (scripts/process_queue.sh zh_docs). Rerun after new links are cleaned: only new URLs are queued and fetched.
# Run from the repo root.
#
# Usage:
#   bash scripts/go_zh_docs.sh
#   N_WORKERS=200 bash scripts/go_zh_docs.sh

set -eo pipefail  # no -u: ~/.myrc references unset vars
source ~/.myrc
mkdir -p logs/scripts/slurm

QUEUE_JOB=$(sbatch --parsable --export=NONE scripts/slurm/zh_docs_queue.slurm)
echo "zh_docs_queue $QUEUE_JOB (log: logs/scripts/slurm/zh_docs_queue_$QUEUE_JOB.out)"
N_WORKERS=${N_WORKERS:-100} DEPENDENCY=afterok:$QUEUE_JOB bash scripts/process_queue.sh zh_docs
