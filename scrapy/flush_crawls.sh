#!/bin/bash
# FLUSH: deletes everything scrapy/crawl_sites.sh writes, for a clean rerun:
#   data/interim/site_crawls/   pages, crawl state (jobdir) and done markers, one dir per site
#   logs/scrapy/                scrapy and SLURM logs
# Refuses while crawl_site jobs are queued or running. Run from the repo root.
#
# Usage:
#   bash scrapy/flush_crawls.sh          # asks before deleting
#   FORCE=1 bash scrapy/flush_crawls.sh  # no prompt

set -eo pipefail

if command -v squeue >/dev/null && [ -n "$(squeue -h -u "$USER" --name=crawl_site)" ]; then
    echo "ERROR: crawl_site jobs are still queued/running; scancel them first"
    exit 1
fi

DIRS=(data/interim/site_crawls logs/scrapy)
echo "WARNING: this deletes:"
printf '  %s/\n' "${DIRS[@]}"
if [ "${FORCE:-}" != 1 ]; then
    read -r -p "Continue? [y/N] " answer
    [ "$answer" = y ] || { echo "Aborted"; exit 1; }
fi

for dir in "${DIRS[@]}"; do
    if [ -d "$dir" ]; then
        # random order spreads the I/O load on the shared filesystem
        find "$dir" -type f | shuf | xargs -r rm -f
        find "$dir" -type d -empty -delete
        echo "  deleted $dir/"
    fi
done
echo "Flushed"
