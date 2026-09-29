#!/bin/bash
# One worker of a shard queue (scripts/process_queue.py). scripts/process_queue.sh submits many.
#
# Usage (from the repo root; normally via scripts/process_queue.sh):
#   sbatch --export=QUEUE_DIR=$TMP/wikipedia_queue/zh,RESULTS_DIR=$TMP/wikipedia_results/zh,PROCESSOR=fetch_status scripts/slurm/process_queue.slurm
#   optional: MAX_SHARDS=1 (test)

#SBATCH --partition=acpu
#SBATCH --time=24:00:00
#SBATCH --job-name=process_queue
#SBATCH --output=logs/scripts/slurm/%x_%j.out
#SBATCH --mem=4G
#SBATCH --qos=cpu-normal
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --mail-type=FAIL
#SBATCH --mail-user=abha4861@colorado.edu

set -eo pipefail  # no -u: ~/.myrc and conda activate reference unset vars
source ~/.myrc

if [ -z "${QUEUE_DIR:-}" ] || [ -z "${RESULTS_DIR:-}" ] || [ -z "${PROCESSOR:-}" ]; then
    echo "ERROR: QUEUE_DIR, RESULTS_DIR and PROCESSOR are required"
    exit 1
fi

module load anaconda
conda activate translation

python -m scripts.process_queue -queue-dir "$QUEUE_DIR" -results-dir "$RESULTS_DIR" -processor "$PROCESSOR" \
    -max-shards "$MAX_SHARDS"
