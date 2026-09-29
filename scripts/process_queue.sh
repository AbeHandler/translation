#!/bin/bash
# Process a shard queue with N_WORKERS SLURM jobs at once (scripts/slurm/process_queue.slurm): each claims shards
# without results and works through their rows one at a time, so N_WORKERS rows run at a time.
# Workers share the work through .lock files, so start as many as you like, and rerun to finish what's left.
# The queue and results live on scratch ($TMP). Run from the repo root.
#
# Usage:
#   QUEUE_DIR=$TMP/cc_news_queue RESULTS_DIR=$TMP/cc_news_results PROCESSOR=link_language bash scripts/process_queue.sh
#   ... N_WORKERS=200 bash scripts/process_queue.sh
#   ... N_WORKERS=1 MAX_SHARDS=1 bash scripts/process_queue.sh     # test: one shard

set -eo pipefail  # no -u: ~/.myrc references unset vars
source ~/.myrc

if [ -z "${QUEUE_DIR:-}" ] || [ -z "${RESULTS_DIR:-}" ] || [ -z "${PROCESSOR:-}" ]; then
    echo "ERROR: QUEUE_DIR, RESULTS_DIR and PROCESSOR are required (see the usage at the top of this script)"
    exit 1
fi
N_WORKERS=${N_WORKERS:-20}
mkdir -p logs/scripts/slurm "$RESULTS_DIR"

EXPORTS="QUEUE_DIR=$QUEUE_DIR,RESULTS_DIR=$RESULTS_DIR,PROCESSOR=$PROCESSOR,MAX_SHARDS=$MAX_SHARDS"
for ((i = 0; i < N_WORKERS; i++)); do
    sbatch --parsable --export="$EXPORTS" scripts/slurm/process_queue.slurm > /dev/null
done
echo "process_queue: $N_WORKERS workers on $QUEUE_DIR ($(ls "$QUEUE_DIR"/shard_*.jsonl | wc -l) shards) -> $RESULTS_DIR"
echo
echo "Spot checks:"
echo "  squeue -u \$USER --name=process_queue | wc -l"
echo "  ls $RESULTS_DIR/shard_*.jsonl | wc -l          # shards done"
echo "  ls $RESULTS_DIR/*.lock                         # in progress (stale if no worker is running)"
echo "  cat $RESULTS_DIR/shard_*.jsonl | jq -r '.error // \"ok\"' | cut -c1-60 | sort | uniq -c | sort -rn | head"
