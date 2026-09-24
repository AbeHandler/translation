#!/bin/bash
# FLUSH: deletes data/interim/site_crawls/ (all scrapy crawl pages, state and done markers).
# Refuses while crawl_site jobs are queued or running.
#
# Usage (from the repo root):
#   sbatch tmp.slurm

#SBATCH --partition=acpu
#SBATCH --time=24:00:00
#SBATCH --job-name=tmp
#SBATCH --output=logs/scripts/slurm/%x_%j.out
#SBATCH --mem=1G
#SBATCH --qos=cpu-normal
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --mail-type=FAIL
#SBATCH --mail-user=abha4861@colorado.edu

set -eo pipefail

if [ -n "$(squeue -h -u "$USER" --name=crawl_site)" ]; then
    echo "ERROR: crawl_site jobs are still queued/running; scancel them first"
    exit 1
fi

echo "WARNING: deleting data/interim/site_crawls/"
rm -rf data/interim/site_crawls/
echo "Deleted"
