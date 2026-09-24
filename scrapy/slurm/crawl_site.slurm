#!/bin/bash
# Crawl one site with the scrapy spider in scrapy/site_crawler. Resumable: the crawl state lives in
# data/interim/site_crawls/<domain>/jobdir, so resubmitting after a time limit picks up where it stopped.
# Scrapy stops itself at 23.5h (CLOSESPIDER_TIMEOUT), before SLURM's 24h kill, so it can save its state
# and finish writing pages.jsonl. Touches data/interim/site_crawls/<domain>/done only when scrapy reports
# the whole site crawled (finish_reason 'finished'), not when it stopped on the timer or MAX_PAGES.
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

STOP_AFTER_SECONDS=84600  # 23.5h: leaves SLURM's 24h limit half an hour for a clean shutdown
LIMIT=()
if [ -n "${MAX_PAGES:-}" ]; then LIMIT=(-s "CLOSESPIDER_PAGECOUNT=$MAX_PAGES"); fi

export PYTHONPATH=$PWD  # so the spider can import src
cd scrapy  # scrapy finds its project through scrapy.cfg in the working directory
touch "$OUT_DIR/pages.jsonl"
PAGES_BEFORE=$(wc -l < "$OUT_DIR/pages.jsonl")
# -o appends, so a resumed crawl adds to the same pages.jsonl
scrapy crawl site -a domain="$DOMAIN" \
    -o "$OUT_DIR/pages.jsonl" \
    -s JOBDIR="$OUT_DIR/jobdir" \
    -s LOG_FILE="$LOG_DIR/$DOMAIN.log" \
    -s CLOSESPIDER_TIMEOUT="$STOP_AFTER_SECONDS" \
    "${LIMIT[@]}"

# The log appends across runs, so the last finish_reason is this run's.
FINISH_REASON=$(grep -o "'finish_reason': '[a-z_]*'" "$LOG_DIR/$DOMAIN.log" | tail -1 | cut -d"'" -f4 || true)
PAGES_AFTER=$(wc -l < "$OUT_DIR/pages.jsonl")
echo "Stopped because: $FINISH_REASON"
echo "Pages this run:  $((PAGES_AFTER - PAGES_BEFORE))  (total $PAGES_AFTER in $OUT_DIR/pages.jsonl)"
if [ "$FINISH_REASON" = finished ]; then
    touch "$OUT_DIR/done"
    echo "Site done"
else
    echo "Not done; rerun scrapy/crawl_sites.sh to resume"
fi
