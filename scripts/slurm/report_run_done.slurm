#!/bin/bash
# Runs after every find_seed_links worker has ended (success or not) and emails once, so a
# 100-worker run sends one "done" email instead of 100. Prints a summary to its log.
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

WORK_DIR=$TMP/find_seed_links
MATCHES=data/processed/cc_link_matches.jsonl

echo "WARCs done:        $(find "$WORK_DIR" -name '*.done' ! -name '*.max*' | wc -l)"
echo "WARCs still locked: $(find "$WORK_DIR" -name '*.lock' | wc -l)   # >0 means a worker died mid-WARC"
if [ -f "$MATCHES" ]; then
    echo "Matches:           $(wc -l < "$MATCHES")  ($MATCHES)"
else
    echo "Matches:           none written; not every WARC is done (see worker logs)"
fi
