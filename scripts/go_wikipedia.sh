#!/bin/bash
# Driver for scripts/wikipedia_pipeline.py: for each language, submits download -> N_PAGE_WORKERS pages workers ->
# filter -> queue, each after the one before, and returns. Every step skips work already done (filter and queue
# rebuild, cheaply), so rerun to finish or refresh. Then process the queue with scripts/process_queue.sh.
# Outputs: $TMP/wikipedia_dumps/, data/interim/wikipedia/<lang>/, $TMP/wikipedia_queue/<lang>/. Run from the repo root.
#
# Usage:
#   bash scripts/go_wikipedia.sh                              # zh and en
#   LANGS=zh N_PAGE_WORKERS=20 bash scripts/go_wikipedia.sh
#   LANGS=zh STEPS=filter,queue bash scripts/go_wikipedia.sh  # after changing the filter in config/wikipedia.yaml
#   LANGS=zh N_PAGE_WORKERS=1 MAX_CHUNKS=1 bash scripts/go_wikipedia.sh   # test: one chunk

set -eo pipefail  # no -u: ~/.myrc references unset vars
source ~/.myrc

if [ -z "${TMP:-}" ]; then
    echo "ERROR: \$TMP is not set; the dumps and the queue go there"
    exit 1
fi
LANGS=${LANGS:-zh en}
STEPS=${STEPS:-download,pages,filter,queue}
N_PAGE_WORKERS=${N_PAGE_WORKERS:-20}
mkdir -p logs/scripts/slurm

ENV_JOB=$(sbatch --parsable --export=NONE scripts/slurm/update_env.slurm)
echo "update_env $ENV_JOB"

submit() {  # submit <lang> <step> <dependency> [how many]; prints :id:id...
    local jobs=""
    for ((i = 0; i < ${4:-1}; i++)); do
        jobs+=":$(sbatch --parsable --job-name="wikipedia_$2" --dependency="$3" --kill-on-invalid-dep=yes \
            --export="WIKI_LANG=$1,STEP=$2,TMP=$TMP,MAX_CHUNKS=$MAX_CHUNKS" scripts/slurm/wikipedia_pipeline.slurm)"
    done
    echo "$jobs"
}

for lang in $LANGS; do
    AFTER=afterok:$ENV_JOB
    if [[ ,$STEPS, == *,download,* ]]; then
        JOBS=$(submit "$lang" download "$AFTER"); AFTER=afterok$JOBS
    fi
    if [[ ,$STEPS, == *,pages,* ]]; then
        JOBS=$(submit "$lang" pages "$AFTER" "$N_PAGE_WORKERS"); AFTER=afterany$JOBS  # filter checks what's done
    fi
    if [[ ,$STEPS, == *,filter,* ]]; then
        JOBS=$(submit "$lang" filter "$AFTER"); AFTER=afterok$JOBS
    fi
    if [[ ,$STEPS, == *,queue,* ]]; then
        JOBS=$(submit "$lang" queue "$AFTER")
    fi
    echo "$lang: $STEPS submitted"
done

echo
echo "Spot checks:"
echo "  squeue -u \$USER --name=wikipedia_download,wikipedia_pages,wikipedia_filter,wikipedia_queue"
echo "  ls data/interim/wikipedia/*/pages/*.parquet | wc -l     # chunks done"
echo "  tail -3 logs/scripts/slurm/wikipedia_filter_*.out       # AI articles kept"
echo "  ls \$TMP/wikipedia_queue/*/ | head                      # queue shards"
