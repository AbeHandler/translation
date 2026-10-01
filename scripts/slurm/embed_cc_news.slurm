#!/bin/bash
# One worker of scripts/embed_cc_news.py: news-similarity embeddings (CPU) of the English CC-NEWS articles whose
# body says "AI", one output file per WARC (data/interim/cc_news_embeddings/). scripts/embed_cc_news.sh submits a
# download job (DOWNLOAD_ONLY=1) and then N of these.
#
# Usage (from the repo root; normally via scripts/embed_cc_news.sh):
#   sbatch --export=NONE scripts/slurm/embed_cc_news.slurm          # TMP comes from ~/.myrc
#   sbatch --export=DOWNLOAD_ONLY=1 scripts/slurm/embed_cc_news.slurm
#   optional: MAX_FILES=1 (test)

#SBATCH --partition=acpu
#SBATCH --time=24:00:00
#SBATCH --job-name=embed_cc_news
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
    echo "ERROR: TMP is required (the model goes in \$TMP/models, the tokenizer in \$TMP/huggingface)"
    exit 1
fi

module load anaconda
conda activate translation

# torch would otherwise start a thread per core on the whole node, not per core this job was given
export OMP_NUM_THREADS=${SLURM_CPUS_PER_TASK:-1}
export HF_HOME=$TMP/huggingface  # shared cache; $HOME's quota is small

# MAX_FILES may be empty; the script treats empty as "no limit".
python -m scripts.embed_cc_news -max-files "$MAX_FILES" ${DOWNLOAD_ONLY:+-download-only}
