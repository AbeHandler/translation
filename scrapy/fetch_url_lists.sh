#!/bin/bash
# Fetch every URL list of one name (scripts/make_crawl_urls.py -name NAME -> site_crawls/<domain>/urls/NAME.txt)
# into the sites' crawl stores: one scrapy/slurm/fetch_urls.slurm job per site. Rerun-safe: each job keeps its own
# state, so pages already fetched aren't fetched again.
#   NAME=hf_hack bash scrapy/fetch_url_lists.sh        (from the repo root, on Alpine)
set -eo pipefail
[ -n "${NAME:-}" ] || { echo "ERROR: NAME is required, e.g. NAME=hf_hack"; exit 1; }
mkdir -p logs/scrapy/slurm
JOB_IDS=""
for list in data/interim/site_crawls/*/urls/"$NAME".txt; do
    [ -s "$list" ] || continue
    domain=$(basename "$(dirname "$(dirname "$list")")")
    JOB=$(sbatch --parsable --export="DOMAIN=$domain,URLS_FILE=$list" scrapy/slurm/fetch_urls.slurm)
    JOB_IDS+=":$JOB"
    echo "$JOB  $domain  $(wc -l < "$list") URLs"
done
[ -n "$JOB_IDS" ] || { echo "ERROR: no lists named $NAME (python -m scripts.make_crawl_urls -name $NAME ...)"; exit 1; }
echo "JOB_IDS=${JOB_IDS#:}"
