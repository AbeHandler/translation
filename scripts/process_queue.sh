#!/bin/bash
# Process a shard queue with N_WORKERS SLURM jobs at once (scripts/slurm/process_queue.slurm): each claims shards
# without results and works through their rows one at a time, so N_WORKERS rows run at a time.
# Workers share the work through .lock files, so start as many as you like, and rerun to finish what's left.
# Name the queue; its directories are under $TMP (from ~/.myrc). Run from the repo root.
#   news          $TMP/cc_news_queue      -> $TMP/cc_news_results       (scripts/cc_news_queue.py)
#   wikipedia_zh  $TMP/wikipedia_queue/zh -> $TMP/wikipedia_results/zh  (scripts/wikipedia_pipeline.py -step queue)
#   wikipedia_en  $TMP/wikipedia_queue/en -> $TMP/wikipedia_results/en
# PROCESSOR (default link_language) is a name from scripts/process_queue.py.
#
# Usage:
#   bash scripts/process_queue.sh news
#   N_WORKERS=200 bash scripts/process_queue.sh wikipedia_zh
#   N_WORKERS=1 MAX_SHARDS=1 bash scripts/process_queue.sh news       # test: one shard
#   QUEUE_DIR=... RESULTS_DIR=... bash scripts/process_queue.sh       # any other queue

set -eo pipefail  # no -u: ~/.myrc references unset vars
source ~/.myrc

if [ -z "${TMP:-}" ]; then
    echo "ERROR: \$TMP is not set (in ~/.myrc); the queues are there"
    exit 1
fi
case "${1:-}" in
    news)          QUEUE_DIR=$TMP/cc_news_queue;      RESULTS_DIR=$TMP/cc_news_results ;;
    wikipedia_zh)  QUEUE_DIR=$TMP/wikipedia_queue/zh; RESULTS_DIR=$TMP/wikipedia_results/zh ;;
    wikipedia_en)  QUEUE_DIR=$TMP/wikipedia_queue/en; RESULTS_DIR=$TMP/wikipedia_results/en ;;
    "")            ;;  # QUEUE_DIR and RESULTS_DIR given directly
    *)             echo "ERROR: unknown queue '$1'; use news, wikipedia_zh or wikipedia_en"; exit 1 ;;
esac
PROCESSOR=${PROCESSOR:-link_language}
if [ -z "${QUEUE_DIR:-}" ] || [ -z "${RESULTS_DIR:-}" ]; then
    echo "ERROR: name a queue (news, wikipedia_zh, wikipedia_en), or set QUEUE_DIR and RESULTS_DIR"
    exit 1
fi
if ! ls "$QUEUE_DIR"/shard_*.jsonl > /dev/null 2>&1; then
    echo "ERROR: no shards in $QUEUE_DIR; build the queue first"
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
