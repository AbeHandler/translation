#!/bin/bash
# Peek at the English screenshots the image screening has found so far in the Chinese site crawls
# (scripts/screen_site_crawl_images.py): counts by kind and site, and 10 random tweets and 10 random prose
# screenshots (page, image URL, OCR text). Only reads.
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
echo "$(echo "$FILES" | wc -l) files screened"
echo "English screenshots by kind:"
cat $FILES | jq -r '.images[] | select(.english_screenshot) | .english_kind // "old rule"' | sort | uniq -c
echo "by site:"
for d in data/interim/site_crawls/*/images; do
    n=$(cat $d/*.jsonl 2>/dev/null | jq '[.images[] | select(.english_screenshot)] | length' | paste -sd+ | bc)
    echo "${n:-0} $(basename $(dirname $d))"
done | sort -rn | head -15
for kind in tweet prose; do
    echo
    echo "10 random $kind screenshots:"
    cat $FILES | jq -c --arg k "$kind" '.url as $p | .images[] | select(.english_kind == $k)
        | {page: $p, src, ocr: .ocr_text[:150]}' | shuf -n 10
done
