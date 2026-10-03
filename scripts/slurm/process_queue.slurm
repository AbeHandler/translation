#!/bin/bash
# One worker of a shard queue (scripts/process_queue.py). scripts/process_queue.sh submits many.
#
# Usage (from the repo root; normally via scripts/process_queue.sh):
#   sbatch --export=QUEUE_DIR=$TMP/cc_news_queue,PROCESSOR=link_language scripts/slurm/process_queue.slurm
#   optional: MAX_SHARDS=1 (test)

#SBATCH --partition=acpu
#SBATCH --time=24:00:00
#SBATCH --job-name=process_queue
#SBATCH --output=logs/scripts/slurm/%x_%j.out
#SBATCH --mem=8G
#SBATCH --qos=cpu-normal
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --mail-type=FAIL
#SBATCH --mail-user=abha4861@colorado.edu

set -eo pipefail  # no -u: ~/.myrc and conda activate reference unset vars
source ~/.myrc

if [ -z "${QUEUE_DIR:-}" ] || [ -z "${PROCESSOR:-}" ]; then
    echo "ERROR: QUEUE_DIR and PROCESSOR are required"
    exit 1
fi

module load anaconda
conda activate translation

export HF_HOME=$TMP/huggingface          # models, shared cache
export TOKENIZERS_PARALLELISM=false

python -m scripts.process_queue -queue-dir "$QUEUE_DIR" -processor "$PROCESSOR" -max-shards "$MAX_SHARDS"
