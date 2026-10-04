#!/bin/bash
# Peek at the English screenshots the image screening has found so far in the Chinese site crawls
# (scripts/screen_site_crawl_images.py): how many, and 10 random ones (page, image URL, OCR text). Only reads.
#
# Usage (from the repo root):
#   sbatch tmp.slurm        # then: cat logs/scripts/slurm/tmp_<jobid>.out

#SBATCH --partition=acpu
#SBATCH --time=00:30:00
#SBATCH --job-name=tmp
#SBATCH --output=logs/scripts/slurm/%x_%j.out
#SBATCH --mem=4G
#SBATCH --qos=cpu-normal
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --mail-type=FAIL
#SBATCH --mail-user=abha4861@colorado.edu

set -eo pipefail  # no -u: ~/.myrc references unset vars
source ~/.myrc

FILES=$(ls data/interim/site_crawls/*/images/*.jsonl)
echo "$(echo "$FILES" | wc -l) files screened; English screenshots so far: \
$(cat $FILES | jq '.n_english_screenshots' | paste -sd+ | bc)"
echo
cat $FILES | jq -c '.url as $p | .images[] | select(.english_screenshot) | {page: $p, src, ocr: .ocr_text[:150]}' \
    | shuf -n 10
