#!/bin/bash
# One worker of scripts/embed_site_crawls.py: embeds (on CPU) every crawled HTML file that has no embeddings
# file yet and isn't claimed by another worker. scripts/embed_site_crawls.sh submits N of these after update_env.
#
# Usage (from the repo root; normally via scripts/embed_site_crawls.sh):
#   sbatch --export=TMP=$TMP scripts/slurm/embed_site_crawls.slurm
#   optional: MAX_FILES=1 (test)

#SBATCH --partition=acpu
#SBATCH --time=24:00:00
#SBATCH --job-name=embed_site_crawls
#SBATCH --output=logs/scripts/slurm/%x_%j.out
#SBATCH --mem=16G
#SBATCH --cpus-per-task=8
#SBATCH --qos=cpu-normal
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --mail-type=FAIL
#SBATCH --mail-user=abha4861@colorado.edu

set -eo pipefail  # no -u: ~/.myrc and conda activate reference unset vars
source ~/.myrc

if [ -z "${TMP:-}" ]; then
    echo "ERROR: TMP is required (the Hugging Face model cache goes in \$TMP/huggingface)"
    exit 1
fi

module load anaconda
conda activate translation

# torch would otherwise start a thread per core on the whole node, not per core this job was given
export OMP_NUM_THREADS=$SLURM_CPUS_PER_TASK
export HF_HOME=$TMP/huggingface  # the model (~400MB) is downloaded once and shared; $HOME's quota is small

# MAX_FILES may be empty; the script treats empty as "no limit".
python -m scripts.embed_site_crawls -max-files "$MAX_FILES"
