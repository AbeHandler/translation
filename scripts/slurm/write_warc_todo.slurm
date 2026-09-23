#!/bin/bash
# Write $TMP/warcs/todo.txt: CC-NEWS WARCs in [START_DATE, END_DATE] without a .done file.
# Submitted by scripts/find_seed_links_go.sh after update_env.
#
# Usage (from the repo root):
#   sbatch --export=START_DATE=20260901,END_DATE=20260923,AWS=/home/abha4861/bin/v2/2.5.4/bin/aws,TMP=$TMP scripts/slurm/write_warc_todo.slurm
#   optional: MAX_N=100 (test runs track their own .done files)

#SBATCH --partition=acpu
#SBATCH --time=00:30:00
#SBATCH --job-name=write_warc_todo
#SBATCH --mem=2G
#SBATCH --qos=normal
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

# MAX_N may be empty; src/cc_news.py treats empty as "no limit".
python src/cc_news.py \
    -step write_warc_todo \
    -start-date "$START_DATE" \
    -end-date "$END_DATE" \
    -aws "$AWS" \
    -work-dir "$TMP/warcs" \
    -max-n "$MAX_N"
