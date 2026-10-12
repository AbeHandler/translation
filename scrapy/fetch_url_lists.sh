#!/bin/bash
# Fetch every URL list of one name (scripts/make_crawl_urls.py -name NAME -> site_crawls/<domain>/urls/NAME.txt)
# into the sites' crawl stores: one scrapy/slurm/fetch_urls.slurm job per site. Rerun-safe: each job keeps its own
# state, so pages already fetched aren't fetched again. One scrapy process per site at a time: a site's fetch waits
# for its queued or running crawl_site and fetch_urls jobs (the site is in each job's comment; scrapy/crawl_sites.sh
# likewise skips a site while a fetch of it is queued or running).
#   NAME=hf_hack bash scrapy/fetch_url_lists.sh        (from the repo root, on Alpine)
set -eo pipefail
[ -n "${NAME:-}" ] || { echo "ERROR: NAME is required, e.g. NAME=hf_hack"; exit 1; }
mkdir -p logs/scrapy/slurm
JOB_IDS=""
for list in data/interim/site_crawls/*/urls/"$NAME".txt; do
    [ -s "$list" ] || continue
    domain=$(basename "$(dirname "$(dirname "$list")")")
    busy=$(squeue -u "$USER" -h -n crawl_site,fetch_urls -o '%i %k' | awk -v d="$domain" '$2 == d {print $1}' | paste -sd: -)
    JOB=$(sbatch --parsable --comment="$domain" ${busy:+--dependency=afterany:$busy} \
        --export="DOMAIN=$domain,URLS_FILE=$list" scrapy/slurm/fetch_urls.slurm)
    JOB_IDS+=":$JOB"
    echo "$JOB  $domain  $(wc -l < "$list") URLs${busy:+  (after $busy: the crawl or fetch of the site)}"
done
[ -n "$JOB_IDS" ] || { echo "ERROR: no lists named $NAME (python -m scripts.make_crawl_urls -name $NAME ...)"; exit 1; }
echo "JOB_IDS=${JOB_IDS#:}"
