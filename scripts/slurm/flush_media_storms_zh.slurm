#!/bin/bash
# FLUSH for a clean rerun of the Chinese media storms (WARNING: deletes data):
#   1. the site crawls' embeddings files with more than 10% of pages unembedded
#      (scripts/flush_empty_site_embeddings.py; the zh-CN language-code bug), so they are embedded again
#   2. everything under data/interim/media_storms_zh (by_day markers, days, links, edges, clusters, storms),
#      made with the old Chinese and AI tests
# Files are deleted in random order. Then: bash scripts/go_media_storms_zh.sh
#
# Usage (from the repo root):
#   sbatch --export=NONE scripts/slurm/flush_media_storms_zh.slurm

#SBATCH --partition=acpu
#SBATCH --time=04:00:00
#SBATCH --job-name=flush_media_storms_zh
#SBATCH --output=logs/scripts/slurm/%x_%j.out
#SBATCH --mem=4G
#SBATCH --qos=cpu-normal
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --mail-type=END,FAIL
#SBATCH --mail-user=abha4861@colorado.edu

set -eo pipefail  # no -u: ~/.myrc and conda activate reference unset vars
source ~/.myrc

module load anaconda
conda activate translation

echo "WARNING: deleting the zh media storms and embeddings files with many empty pages"
python -m scripts.flush_empty_site_embeddings
if [ -d data/interim/media_storms_zh ]; then
    find data/interim/media_storms_zh -type f | shuf | xargs -r rm -f
    find data/interim/media_storms_zh -type d -empty -delete 2>/dev/null || true
    echo "deleted data/interim/media_storms_zh"
fi
