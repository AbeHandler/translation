#!/bin/bash
# Process a shard queue with N_WORKERS SLURM jobs at once (scripts/slurm/process_queue.slurm): each claims shards
# without results and works through their rows one at a time, so N_WORKERS rows run at a time.
# Workers share the work through .lock files, so start as many as you like, and rerun to finish what's left.
# After the workers, a collect job (scripts/slurm/collect_queue.slurm) merges all results, deduplicated, into one
# file and emails when done; its log has the summary (shards done, languages, errors).
# Name the queue; it lives under $TMP (from ~/.myrc), its results in <queue>/results/. Run from the repo root.
#   news          $TMP/cc_news_queue       -> data/processed/news_link_languages.jsonl        (scripts/cc_news_queue.py)
#   wikipedia_zh  $TMP/wikipedia_queue/zh  -> data/processed/wikipedia_zh_link_languages.jsonl (wikipedia_pipeline.py)
#   wikipedia_en  $TMP/wikipedia_queue/en  -> data/processed/wikipedia_en_link_languages.jsonl
#   COLLECT_ONLY=1 bash scripts/process_queue.sh news    # just collect (and see the summary) now
# PROCESSOR (default link_language) is a name from scripts/process_queue.py.
#
# Usage:
#   bash scripts/process_queue.sh news
#   N_WORKERS=200 bash scripts/process_queue.sh wikipedia_zh
#   N_WORKERS=1 MAX_SHARDS=1 bash scripts/process_queue.sh news       # test: one shard
#   QUEUE_DIR=... bash scripts/process_queue.sh                       # any other queue

set -eo pipefail  # no -u: ~/.myrc references unset vars
source ~/.myrc

if [ -z "${TMP:-}" ]; then
    echo "ERROR: \$TMP is not set (in ~/.myrc); the queues are there"
    exit 1
fi
case "${1:-}" in
    news)          QUEUE_DIR=$TMP/cc_news_queue;      OUT=data/processed/news_link_languages.jsonl ;;
    wikipedia_zh)  QUEUE_DIR=$TMP/wikipedia_queue/zh; OUT=data/processed/wikipedia_zh_link_languages.jsonl ;;
    wikipedia_en)  QUEUE_DIR=$TMP/wikipedia_queue/en; OUT=data/processed/wikipedia_en_link_languages.jsonl ;;
    "")            OUT=${OUT:-$QUEUE_DIR/collected.jsonl} ;;  # QUEUE_DIR given directly
    *)             echo "ERROR: unknown queue '$1'; use news, wikipedia_zh or wikipedia_en"; exit 1 ;;
esac
PROCESSOR=${PROCESSOR:-link_language}
if [ -z "${QUEUE_DIR:-}" ]; then
    echo "ERROR: name a queue (news, wikipedia_zh, wikipedia_en), or set QUEUE_DIR"
    exit 1
fi
mkdir -p logs/scripts/slurm
if [ "${COLLECT_ONLY:-}" = 1 ]; then
    JOB=$(sbatch --parsable --export="QUEUE_DIR=$QUEUE_DIR,OUT=$OUT" scripts/slurm/collect_queue.slurm)
    echo "collect_queue $JOB -> $OUT (summary in logs/scripts/slurm/collect_queue_$JOB.out)"
    exit 0
fi
if ! ls "$QUEUE_DIR"/shard_*.jsonl > /dev/null 2>&1; then
    echo "ERROR: no shards in $QUEUE_DIR: build the queue first (or everything in it is done: see $QUEUE_DIR/results)"
    exit 1
fi
N_WORKERS=${N_WORKERS:-20}
RESULTS_DIR=$QUEUE_DIR/results
mkdir -p logs/scripts/slurm "$RESULTS_DIR"

EXPORTS="QUEUE_DIR=$QUEUE_DIR,PROCESSOR=$PROCESSOR,MAX_SHARDS=$MAX_SHARDS"
JOBS=""
for ((i = 0; i < N_WORKERS; i++)); do
    JOBS+=":$(sbatch --parsable --export="$EXPORTS" scripts/slurm/process_queue.slurm)"
done
COLLECT_JOB=$(sbatch --parsable --dependency=afterany"$JOBS" --export="QUEUE_DIR=$QUEUE_DIR,OUT=$OUT" \
    scripts/slurm/collect_queue.slurm)
echo "collect_queue $COLLECT_JOB after them -> $OUT (summary in logs/scripts/slurm/collect_queue_$COLLECT_JOB.out)"
echo "process_queue: $N_WORKERS workers on $QUEUE_DIR ($(ls "$QUEUE_DIR"/shard_*.jsonl | wc -l) shards) -> $RESULTS_DIR"
echo
echo "Spot checks:"
echo "  squeue -u \$USER --name=process_queue | wc -l"
echo "  ls $RESULTS_DIR/shard_*.jsonl | wc -l          # shards done"
echo "  ls $RESULTS_DIR/*.lock                         # in progress (stale if no worker is running)"
echo "  cat $RESULTS_DIR/shard_*.jsonl | jq -r '.error // \"ok\"' | cut -c1-60 | sort | uniq -c | sort -rn | head"
