#!/bin/bash
# One step of scripts/cc_news_pipeline.py (STEP=download|html|links|ner|match). All but match run as many
# workers that share the work; match runs once, after links. scripts/go.sh submits them in order, named
# cc_news_<step>, and gives ner more CPUs and memory (--cpus-per-task, --mem on the sbatch line).
#
# Usage (from the repo root; normally via scripts/go.sh):
#   sbatch --job-name=cc_news_html --export=STEP=html,START_DATE=20260901,END_DATE=20260923,AWS=/home/abha4861/bin/v2/2.5.4/bin/aws,TMP=$TMP scripts/slurm/cc_news_pipeline.slurm
#   optional: MAX_N=100, MAX_WARCS=1 (test), PARTIAL=1 (match what there is)

#SBATCH --partition=acpu
#SBATCH --time=24:00:00
#SBATCH --job-name=cc_news_pipeline
#SBATCH --output=logs/scripts/slurm/%x_%j.out
#SBATCH --mem=8G
#SBATCH --qos=cpu-normal
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --mail-type=FAIL
#SBATCH --mail-user=abha4861@colorado.edu

set -eo pipefail  # no -u: ~/.myrc and conda activate reference unset vars
source ~/.myrc  # first, so $TMP etc. from ~/.myrc are set before the checks below

if [ -z "${STEP:-}" ] || [ -z "${START_DATE:-}" ] || [ -z "${END_DATE:-}" ] || [ -z "${AWS:-}" ] || [ -z "${TMP:-}" ]; then
    echo "ERROR: STEP (download|html|links|ner|match), START_DATE, END_DATE (YYYYMMDD), AWS (path to aws CLI) and TMP are required"
    exit 1
fi

module load anaconda
conda activate translation

# torch (ner) would otherwise start a thread per core on the whole node, not per core this job was given
export OMP_NUM_THREADS=${SLURM_CPUS_PER_TASK:-1}

# MAX_N and MAX_WARCS may be empty; the script treats empty as "no limit".
python -m scripts.cc_news_pipeline \
    -step "$STEP" \
    -start-date "$START_DATE" \
    -end-date "$END_DATE" \
    -aws "$AWS" \
    -work-dir "$TMP/extract_warc_html" \
    -warc-cache-dir "$TMP/cc_news_warcs" \
    -max-n "$MAX_N" \
    -max-warcs "$MAX_WARCS" \
    ${PARTIAL:+-partial}
