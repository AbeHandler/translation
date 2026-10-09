#!/bin/bash
# Publication dates for the embedded English CC-NEWS articles (scripts/date_cc_news.py): N_WORKERS workers sharing
# the WARCs; rerun any time, WARCs with a dates file are skipped. Run from the repo root.
#
# Usage:
#   bash scripts/date_cc_news.sh                          # 200 workers
#   N_WORKERS=1 MAX_FILES=1 bash scripts/date_cc_news.sh  # test: one WARC
#   DEPENDENCY=afterany:<id>:<id> bash scripts/date_cc_news.sh   # workers wait for those jobs (main/step0/go_step0.sh)
# Last line printed: JOB_IDS=<id>:<id>..., for chaining.

set -eo pipefail  # no -u: ~/.myrc references unset vars
source ~/.myrc
mkdir -p logs/scripts/slurm
N_WORKERS=${N_WORKERS:-200}
JOB_IDS=""
for ((i = 0; i < N_WORKERS; i++)); do
    JOB_IDS+=":$(sbatch --parsable ${DEPENDENCY:+--dependency=$DEPENDENCY} --export="MAX_FILES=$MAX_FILES" \
        scripts/slurm/date_cc_news.slurm)"
done
echo "date_cc_news  $N_WORKERS workers${DEPENDENCY:+ after $DEPENDENCY}"
echo
echo "Spot checks:"
echo "  ls data/interim/cc_news_pubdates | grep -c 'parquet\$'      # WARCs done (of ~21.7k)"
echo "  grep -h 'done ' \$(ls -t logs/scripts/slurm/date_cc_news_*.out | head -3) | tail -3   # articles, with pubdate, seconds"
echo "JOB_IDS=${JOB_IDS#:}"   # for launchers that chain after the workers
