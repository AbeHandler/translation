#!/bin/bash
# Collect a shard queue's results into one deduplicated JSONL (scripts/collect_queue.py) and print a summary.
# scripts/process_queue.sh submits it after its workers; the summary is in this job's log.
#
# Usage (from the repo root):
#   sbatch --export="QUEUE_DIR=$TMP/cc_news_queue,OUT=data/processed/news_en_zh_links.jsonl,WHERE=src_language=en&language=zh" \
#       scripts/slurm/collect_queue.slurm
#   WHERE (optional): field=value&field=value, only the rows matching all of them are written
#   KEY (default srcpage,url): fields identifying a row; COUNT (default language): field to count values of

#SBATCH --partition=acpu
#SBATCH --time=12:00:00
#SBATCH --job-name=collect_queue
#SBATCH --output=logs/scripts/slurm/%x_%j.out
#SBATCH --mem=32G
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

python -m scripts.collect_queue -queue-dir "$QUEUE_DIR" -out "$OUT" -where "${WHERE:-}" \
    -key "${KEY:-srcpage,url}" -count "${COUNT:-language}"
