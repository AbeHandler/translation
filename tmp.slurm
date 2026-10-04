#!/bin/bash
# Peek at the English screenshots the image screening has found so far in the Chinese site crawls
# (scripts/screen_site_crawl_images.py): counts by kind and site, and a random sample of 150 tweets and 150 prose
# screenshots -> data/processed/screenshot_sample.jsonl (site, page, image URL, OCR text). Only reads the results.
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
done | sort -rn | head -15 || true   # head closing the pipe early is fine
# a random sample to look through: 150 of each kind, with the site, page, image link and OCR text
SAMPLE=data/processed/screenshot_sample.jsonl
cat $FILES | jq -c '.url as $p | ($p | split("/") | .[2]) as $site | .images[] | select(.english_screenshot)
    | {kind: (.english_kind // "old rule"), site: $site, page: $p, src: .src, label: .label,
       latin_conf: .latin_conf, ocr: .ocr_text}' \
    > "$TMP/screenshots_all.jsonl"
for kind in tweet prose; do
    grep "\"kind\":\"$kind\"" "$TMP/screenshots_all.jsonl" | shuf -n 150 || true
done > "$SAMPLE"
echo
echo "$(wc -l < "$SAMPLE") sampled -> $SAMPLE"
for kind in tweet prose; do
    echo
    echo "5 random $kind screenshots:"
    grep "\"kind\":\"$kind\"" "$SAMPLE" | head -5 | jq -c '{page, src, ocr: .ocr[:150]}' || true
done
