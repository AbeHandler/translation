#!/bin/bash
# One worker of scripts/find_seed_links.py: runs every step for the date range, skipping WARCs that are done
# or claimed by another worker. scripts/go.sh submits N of these after update_env.
#
# Usage (from the repo root; normally via scripts/go.sh):
#   sbatch --export=START_DATE=20260901,END_DATE=20260923,AWS=/home/abha4861/bin/v2/2.5.4/bin/aws,TMP=$TMP scripts/slurm/find_seed_links.slurm
#   optional: MAX_N=100, MAX_WARCS=1

#SBATCH --partition=acpu
#SBATCH --time=24:00:00
#SBATCH --job-name=find_seed_links
#SBATCH --output=logs/scripts/slurm/%x_%j.out
#SBATCH --mem=8G
#SBATCH --qos=cpu-normal
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --mail-type=FAIL
#SBATCH --mail-user=abha4861@colorado.edu

set -eo pipefail  # no -u: ~/.myrc and conda activate reference unset vars
source ~/.myrc  # first, so $TMP etc. from ~/.myrc are set before the checks below

if [ -z "${START_DATE:-}" ] || [ -z "${END_DATE:-}" ] || [ -z "${AWS:-}" ] || [ -z "${TMP:-}" ]; then
    echo "ERROR: START_DATE, END_DATE (YYYYMMDD), AWS (path to aws CLI) and TMP are required"
    exit 1
fi

module load anaconda
conda activate translation

# MAX_N and MAX_WARCS may be empty; the script treats empty as "no limit".
python -m scripts.find_seed_links \
    -start-date "$START_DATE" \
    -end-date "$END_DATE" \
    -aws "$AWS" \
    -work-dir "$TMP/find_seed_links" \
    -warc-cache-dir "$TMP/cc_news_warcs" \
    -max-n "$MAX_N" \
    -max-warcs "$MAX_WARCS"
