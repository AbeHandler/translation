#!/bin/bash
# Fetch a list of URLs of one site into its crawl store (the spider's list mode: only those pages, nothing followed):
# raw HTML to data/interim/site_crawls/<domain>/html/ (same files as the crawl, so embedding, the storms and fightin
# pick them up), pages to <domain>/pages_urls.jsonl. Its own job state (jobdir_urls_<list name>), so it can run
# beside the site's crawl and resumes after a time limit. URL lists: scripts/make_crawl_urls.py.
#
# Usage (from the repo root):
#   sbatch --export=DOMAIN=ithome.com,URLS_FILE=data/interim/site_crawls/ithome.com/urls/hf_hack.txt scrapy/slurm/fetch_urls.slurm

#SBATCH --partition=acpu
#SBATCH --time=24:00:00
#SBATCH --job-name=fetch_urls
#SBATCH --output=logs/scrapy/slurm/%x_%j.out
#SBATCH --mem=8G
#SBATCH --qos=cpu-normal
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --mail-type=FAIL,END
#SBATCH --mail-user=abha4861@colorado.edu

set -eo pipefail  # no -u: ~/.myrc and conda activate reference unset vars
source ~/.myrc
if [ -z "${DOMAIN:-}" ] || [ ! -s "${URLS_FILE:-}" ]; then
    echo "ERROR: DOMAIN and a non-empty URLS_FILE are required"
    exit 1
fi
module load anaconda
conda activate translation

OUT_DIR=$PWD/data/interim/site_crawls/$DOMAIN
URLS_FILE=$(realpath "$URLS_FILE")
NAME=$(basename "$URLS_FILE" .txt)
mkdir -p "$OUT_DIR" "$PWD/logs/scrapy"
export PYTHONPATH=$PWD
cd scrapy
echo "fetching $(wc -l < "$URLS_FILE") URLs of $DOMAIN from $URLS_FILE"
scrapy crawl site -a domain="$DOMAIN" -a urls_file="$URLS_FILE" \
    -o "$OUT_DIR/pages_urls.jsonl" \
    -s JOBDIR="$OUT_DIR/jobdir_urls_$NAME" \
    -s HTML_DIR="$OUT_DIR/html" \
    -s LOG_FILE="$PWD/../logs/scrapy/${DOMAIN}_urls_$NAME.log" \
    -s CLOSESPIDER_TIMEOUT=84600 \
    -s CONCURRENT_REQUESTS_PER_DOMAIN=4     # half the crawl's 8: often beside the site's own crawl
grep -o "'downloader/response_status_count/[0-9]*': [0-9]*" "$PWD/../logs/scrapy/${DOMAIN}_urls_$NAME.log" | tail -5
