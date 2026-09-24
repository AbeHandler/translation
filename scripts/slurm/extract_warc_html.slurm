#!/bin/bash
# One worker of scripts/extract_warc_html.py: saves the raw HTML of every en/zh article in each WARC
# of the date range to data/interim/cc_html/<warc>.parquet, skipping WARCs that are done or claimed
# by another worker. scripts/go.sh submits N of these after update_env.
#
# Usage (from the repo root; normally via scripts/go.sh):
#   sbatch --export=START_DATE=20260901,END_DATE=20260923,AWS=/home/abha4861/bin/v2/2.5.4/bin/aws,TMP=$TMP scripts/slurm/extract_warc_html.slurm
#   optional: MAX_N=100, MAX_WARCS=1

#SBATCH --partition=acpu
#SBATCH --time=24:00:00
#SBATCH --job-name=extract_warc_html
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
python -m scripts.extract_warc_html \
    -start-date "$START_DATE" \
    -end-date "$END_DATE" \
    -aws "$AWS" \
    -work-dir "$TMP/extract_warc_html" \
    -max-n "$MAX_N" \
    -max-warcs "$MAX_WARCS"
