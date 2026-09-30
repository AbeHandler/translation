#!/bin/bash
# One step of scripts/cc_news_pipeline.py (STEP=download|html|links|ner|match). All but match run as many
# workers that share the work; match runs once, after links. scripts/go_zh_en.sh submits them in order, named
# cc_news_<step>, and gives ner more CPUs and memory (--cpus-per-task, --mem on the sbatch line).
#
# Usage (from the repo root; normally via scripts/go_zh_en.sh):
#   sbatch --job-name=cc_news_html --export=STEP=html,START_DATE=20260901,END_DATE=20260923 scripts/slurm/cc_news_pipeline.slurm
#   (TMP comes from ~/.myrc; AWS defaults to the aws CLI v2 on Alpine)
#   optional: MAX_N=100, MAX_WARCS=1 (test), PARTIAL=1 (match what there is)
#   links and ner without START_DATE/END_DATE: every HTML file there is

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

AWS=${AWS:-/home/abha4861/bin/v2/2.5.4/bin/aws}  # aws CLI v2 on Alpine (an alias there, so not on PATH in jobs)
if [ -z "${STEP:-}" ] || [ -z "${TMP:-}" ]; then
    echo "ERROR: STEP (download|html|links|ner|match) is required, and TMP (from ~/.myrc);"
    echo "       START_DATE and END_DATE (YYYYMMDD) too, except for links and ner"
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
