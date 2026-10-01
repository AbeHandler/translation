#!/bin/bash
# Submit one scrapy crawl per site in config/sites.txt (scrapy/slurm/crawl_site.slurm), in random order,
# after update_env. Sites with a done marker, or with a crawl_site job already queued or running, are skipped,
# so rerunning resumes unfinished crawls.
# Output: data/interim/site_crawls/<domain>/pages.jsonl (one line per page: url, title, pubdate, links)
#         and <domain>/html/*.parquet (raw HTML, same format as CC-NEWS data/interim/cc_html).
# Logs: logs/scrapy/<domain>.log and logs/scrapy/slurm/. Clean slate: sbatch --export=NONE scrapy/slurm/flush_crawls.slurm
#
# Usage (from the repo root):
#   bash scrapy/crawl_sites.sh
#   MAX_PAGES=50 bash scrapy/crawl_sites.sh   # test: stop each crawl after 50 pages
# DEPENDENCY=afterok:<job id> makes the crawls wait on that job instead of a new update_env
# (scripts/go_en_zh.sh does this). The last line printed is JOB_IDS=<id>:<id>:... of the crawls.

set -eo pipefail  # no -u: ~/.myrc references unset vars
source ~/.myrc

SITES=config/sites.txt  # one bare domain or start URL per line
DOMAINS=$(grep -v -e '^#' -e '^[[:space:]]*$' "$SITES" | shuf)
if [ -z "$DOMAINS" ]; then
    echo "ERROR: no sites in $SITES (one bare domain per line)"
    exit 1
fi
mkdir -p logs/scrapy/slurm logs/scripts/slurm  # SLURM won't create the --output dirs

if [ -z "${DEPENDENCY:-}" ]; then
    # --export=NONE: don't inherit the login node's modules (see scripts/go_zh_en.sh)
    ENV_JOB=$(sbatch --parsable --export=NONE scripts/slurm/update_env.slurm)
    echo "update_env  $ENV_JOB"
    DEPENDENCY=afterok:$ENV_JOB
fi

# sites with a crawl already queued or running (its domain is in the job's comment), so none is crawled twice
RUNNING=$(squeue -u "$USER" -h -n crawl_site -o '%k')
JOB_IDS=""
n_submitted=0
n_done=0
n_running=0
for site in $DOMAINS; do
    # a line is a bare domain (denverpost.com) or a URL to start from (https://epaper.gmw.cn/gmrbdb/): the
    # crawl's name and output folder are its host without www.
    domain=$(echo "$site" | sed -E 's#^[a-zA-Z]+://##; s#[/?].*##; s#^www\.##')
    START_URL=""
    if [ "$site" != "$domain" ]; then START_URL=$site; fi
    if [ -e "data/interim/site_crawls/$domain/done" ]; then
        n_done=$((n_done + 1))
        continue
    fi
    if grep -qxF "$domain" <<< "$RUNNING"; then
        n_running=$((n_running + 1))
        continue
    fi
    JOB=$(sbatch --parsable --dependency="$DEPENDENCY" --kill-on-invalid-dep=yes --comment="$domain" \
        --export="DOMAIN=$domain,START_URL=$START_URL,MAX_PAGES=$MAX_PAGES" scrapy/slurm/crawl_site.slurm)
    JOB_IDS+=":$JOB"
    n_submitted=$((n_submitted + 1))
done
echo "crawl_site  $n_submitted submitted, $n_done already done, $n_running already queued or running"

echo
echo "Spot checks:"
echo "  squeue -u \$USER --name=update_env,crawl_site"
echo "  ls data/interim/site_crawls/*/done | wc -l                  # sites finished"
echo "  wc -l data/interim/site_crawls/*/pages.jsonl                # pages per site"
echo "  head -c 500 data/interim/site_crawls/<domain>/pages.jsonl"
echo "  grep -c ERROR logs/scrapy/*.log"
echo "JOB_IDS=${JOB_IDS#:}"
