#!/bin/bash
# Collect a shard queue's results into one deduplicated JSONL (scripts/collect_queue.py) and print a summary.
# scripts/process_queue.sh submits it after its workers; the summary is in this job's log.
#
# Usage (from the repo root):
#   sbatch --export=QUEUE_DIR=$TMP/cc_news_queue,OUT=data/processed/news_link_languages.jsonl scripts/slurm/collect_queue.slurm

#SBATCH --partition=acpu
#SBATCH --time=02:00:00
#SBATCH --job-name=collect_queue
#SBATCH --output=logs/scripts/slurm/%x_%j.out
#SBATCH --mem=16G
#SBATCH --qos=cpu-normal
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --mail-type=END,FAIL
#SBATCH --mail-user=abha4861@colorado.edu

set -eo pipefail  # no -u: ~/.myrc and conda activate reference unset vars
source ~/.myrc

if [ -z "${QUEUE_DIR:-}" ] || [ -z "${OUT:-}" ]; then
    echo "ERROR: QUEUE_DIR and OUT are required"
    exit 1
fi

module load anaconda
conda activate translation

python -m scripts.collect_queue -queue-dir "$QUEUE_DIR" -out "$OUT"
