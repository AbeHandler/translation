#!/bin/bash
# Runs after every worker (find_seed_links and extract_warc_html) has ended, success or not, and
# emails once, so a 100-worker run sends one "done" email instead of 100. Prints a summary to its log.
# Submitted by scripts/go.sh.
#
# Usage (from the repo root; normally via scripts/go.sh):
#   sbatch --export=TMP=$TMP --dependency=afterany:<worker ids> scripts/slurm/report_run_done.slurm

#SBATCH --partition=acpu
#SBATCH --time=00:10:00
#SBATCH --job-name=report_run_done
#SBATCH --output=logs/scripts/slurm/%x_%j.out
#SBATCH --mem=1G
#SBATCH --qos=cpu-normal
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --mail-type=END,FAIL
#SBATCH --mail-user=abha4861@colorado.edu

set -eo pipefail  # no -u: ~/.myrc references unset vars
source ~/.myrc

MATCHES=data/processed/cc_link_matches.jsonl

for STEP in find_seed_links extract_warc_html; do
    WORK_DIR=$TMP/$STEP
    [ -d "$WORK_DIR" ] || continue
    echo "$STEP"
    echo "  WARCs done:         $(find "$WORK_DIR" -name '*.done' ! -name '*.max*' | wc -l)"
    echo "  WARCs still locked: $(find "$WORK_DIR" -name '*.lock' | wc -l)   # >0 means a worker died mid-WARC"
done
if [ -f "$MATCHES" ]; then
    echo "Seed-link matches: $(wc -l < "$MATCHES")  ($MATCHES)"
else
    echo "Seed-link matches: none written; not every WARC is done (see find_seed_links logs)"
fi
echo "HTML Parquet files: $(find data/interim/cc_html -name '*.parquet' ! -name '*.max*' 2>/dev/null | wc -l)"
