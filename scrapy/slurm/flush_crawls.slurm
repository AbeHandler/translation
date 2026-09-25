#!/bin/bash
# FLUSH: deletes everything scripts/site_crawls_go.sh writes, for a clean rerun:
#   data/interim/site_crawls/          pages, HTML, embeddings, crawl state (jobdir) and done markers, per site
#   data/processed/site_crawls_annoy/  the Annoy index
#   logs/scrapy/                       scrapy and crawl SLURM logs
# Submitting it is the confirmation: there is no prompt. Refuses while any of the pipeline's jobs are queued or
# running (scancel them first). Deletes files in random order, which spreads the load on the shared filesystem.
#
# Usage (from the repo root):
#   sbatch --export=NONE scrapy/slurm/flush_crawls.slurm

#SBATCH --partition=acpu
#SBATCH --time=24:00:00
#SBATCH --job-name=flush_crawls
#SBATCH --output=logs/scripts/slurm/%x_%j.out
#SBATCH --mem=4G
#SBATCH --qos=cpu-normal
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --mail-type=FAIL
#SBATCH --mail-user=abha4861@colorado.edu

set -eo pipefail

JOBS=update_env,crawl_site,embed_site_crawls,build_annoy_index
if [ -n "$(squeue -h -u "$USER" --name=$JOBS)" ]; then
    echo "ERROR: $JOBS jobs are still queued/running; scancel them first:"
    squeue -u "$USER" --name=$JOBS
    exit 1
fi

DIRS=(data/interim/site_crawls data/processed/site_crawls_annoy logs/scrapy)
echo "WARNING: deleting:"
printf '  %s/\n' "${DIRS[@]}"
for dir in "${DIRS[@]}"; do
    if [ -d "$dir" ]; then
        find "$dir" -type f | shuf | xargs -r rm -f
        find "$dir" -type d -empty -delete
        echo "  deleted $dir/"
    fi
done
echo "Flushed"
