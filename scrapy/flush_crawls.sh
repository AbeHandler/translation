#!/bin/bash
# FLUSH: deletes everything scripts/site_crawls_go.sh writes, for a clean rerun:
#   data/interim/site_crawls/          pages, HTML, embeddings, crawl state (jobdir) and done markers, per site
#   data/processed/site_crawls_annoy/  the Annoy index
#   logs/scrapy/                       scrapy and crawl SLURM logs
# Refuses while any of its jobs are queued or running. Run from the repo root.
#
# Usage:
#   bash scrapy/flush_crawls.sh          # asks before deleting
#   FORCE=1 bash scrapy/flush_crawls.sh  # no prompt

set -eo pipefail

JOBS=crawl_site,embed_site_crawls,build_annoy_index
if command -v squeue >/dev/null && [ -n "$(squeue -h -u "$USER" --name=$JOBS)" ]; then
    echo "ERROR: $JOBS jobs are still queued/running; scancel them first"
    exit 1
fi

DIRS=(data/interim/site_crawls data/processed/site_crawls_annoy logs/scrapy)
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
