#!/bin/bash
# Crawl one site with the scrapy spider in scrapy/site_crawler. Resumable: the crawl state lives in
# data/interim/site_crawls/<domain>/jobdir, so resubmitting after a time limit picks up where it stopped.
# Touches data/interim/site_crawls/<domain>/done when a full (no MAX_PAGES) crawl finishes.
#
# Usage (from the repo root; normally via scrapy/crawl_sites.sh):
#   sbatch --export=DOMAIN=denverpost.com scrapy/slurm/crawl_site.slurm
#   sbatch --export=DOMAIN=denverpost.com,MAX_PAGES=50 scrapy/slurm/crawl_site.slurm   # test

#SBATCH --partition=acpu
#SBATCH --time=24:00:00
#SBATCH --job-name=crawl_site
#SBATCH --output=logs/scrapy/slurm/%x_%j.out
#SBATCH --mem=8G
#SBATCH --qos=cpu-normal
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --mail-type=FAIL
#SBATCH --mail-user=abha4861@colorado.edu

set -eo pipefail  # no -u: ~/.myrc and conda activate reference unset vars
source ~/.myrc

if [ -z "${DOMAIN:-}" ]; then
    echo "ERROR: DOMAIN is required, e.g. --export=DOMAIN=denverpost.com"
    exit 1
fi

module load anaconda
conda activate translation

OUT_DIR=$PWD/data/interim/site_crawls/$DOMAIN
LOG_DIR=$PWD/logs/scrapy
mkdir -p "$OUT_DIR" "$LOG_DIR"

LIMIT=()
if [ -n "${MAX_PAGES:-}" ]; then LIMIT=(-s "CLOSESPIDER_PAGECOUNT=$MAX_PAGES"); fi

export PYTHONPATH=$PWD  # so the spider can import src
cd scrapy  # scrapy finds its project through scrapy.cfg in the working directory
# -o appends, so a resumed crawl adds to the same pages.jsonl
scrapy crawl site -a domain="$DOMAIN" \
    -o "$OUT_DIR/pages.jsonl" \
    -s JOBDIR="$OUT_DIR/jobdir" \
    -s LOG_FILE="$LOG_DIR/$DOMAIN.log" \
    "${LIMIT[@]}"

if [ -z "${MAX_PAGES:-}" ]; then touch "$OUT_DIR/done"; fi
echo "Pages so far: $(wc -l < "$OUT_DIR/pages.jsonl")  ($OUT_DIR/pages.jsonl)"
