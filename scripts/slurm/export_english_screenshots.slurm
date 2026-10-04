#!/bin/bash
# Every English screenshot found in the site crawls so far (scripts/export_english_screenshots.py)
# -> data/processed/english_screenshot_links.tsv (kind, site, page, image URL, OCR confidence, notable flag and
# accounts, OCR text). First downloads the notable X accounts from Wikidata (scripts/fetch_notable_accounts.py;
# skipped once data/external/notable_accounts.tsv exists).
#
# Usage (from the repo root):
#   sbatch --export=NONE scripts/slurm/export_english_screenshots.slurm

#SBATCH --partition=acpu
#SBATCH --time=01:00:00
#SBATCH --job-name=export_english_screenshots
#SBATCH --output=logs/scripts/slurm/%x_%j.out
#SBATCH --mem=8G
#SBATCH --qos=cpu-normal
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --mail-type=FAIL
#SBATCH --mail-user=abha4861@colorado.edu

set -eo pipefail  # no -u: ~/.myrc and conda activate reference unset vars
source ~/.myrc

module load anaconda
conda activate translation

python -m scripts.fetch_notable_accounts
python -m scripts.export_english_screenshots
