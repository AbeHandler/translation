#!/bin/bash
# FLUSH (WARNING: deletes data): every output of one corpus's media storms, for a clean rerun
#   CORPUS=en (default): data/interim/media_storms     CORPUS=zh: data/interim/media_storms_zh
# (by_day markers, days, links, edges, clusters, storms, seeds). Inputs (embeddings, dates, crawls) are kept.
# Files are deleted in random order. Normally run by FLUSH=1 bash scripts/go_media_storms[_zh].sh.
#
# Usage (from the repo root):
#   sbatch --export=CORPUS=zh scripts/slurm/flush_media_storms.slurm

#SBATCH --partition=acpu
#SBATCH --time=04:00:00
#SBATCH --job-name=flush_media_storms
#SBATCH --output=logs/scripts/slurm/%x_%j.out
#SBATCH --mem=2G
#SBATCH --qos=cpu-normal
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --mail-type=FAIL
#SBATCH --mail-user=abha4861@colorado.edu

set -eo pipefail  # no -u: ~/.myrc references unset vars
source ~/.myrc

DIR=data/interim/media_storms
[ "${CORPUS:-en}" = zh ] && DIR=data/interim/media_storms_zh
echo "WARNING: deleting $DIR"
if [ -d "$DIR" ]; then
    find "$DIR" -type f | shuf | xargs -r rm -f
    find "$DIR" -type d -empty -delete 2>/dev/null || true
fi
echo "deleted $DIR"
