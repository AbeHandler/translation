#!/bin/bash
# Re-apply the English-screenshot test to the site crawls' saved OCR (scripts/rescore_site_crawl_images.py):
# rewrites data/interim/site_crawls/*/images/*.jsonl in place; nothing is fetched or OCR'd again.
#
# Usage (from the repo root):
#   sbatch --export=NONE scripts/slurm/rescore_site_crawl_images.slurm

#SBATCH --partition=acpu
#SBATCH --time=02:00:00
#SBATCH --job-name=rescore_site_crawl_images
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

python -m scripts.rescore_site_crawl_images
