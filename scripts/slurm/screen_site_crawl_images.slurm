#!/bin/bash
# One worker of scripts/screen_site_crawl_images.py: screens the images of the Chinese site crawls' AI articles
# for English screenshots (site_crawls/<domain>/html/<part>.parquet -> <domain>/images/<part>.jsonl; image URLs,
# never images). scripts/screen_site_crawl_images.sh submits N of these. Needs Tesseract in the env and its eng +
# chi_sim files in $TMP/tessdata (scripts/slurm/update_env.slurm sets both up).
#
# Usage (from the repo root; normally via scripts/screen_site_crawl_images.sh):
#   sbatch --export=NONE scripts/slurm/screen_site_crawl_images.slurm
#   optional: MAX_FILES=1 (test)

#SBATCH --partition=acpu
#SBATCH --time=24:00:00
#SBATCH --job-name=screen_site_crawl_images
#SBATCH --output=logs/scripts/slurm/%x_%j.out
#SBATCH --mem=8G
#SBATCH --cpus-per-task=4
#SBATCH --qos=cpu-normal
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --mail-type=FAIL
#SBATCH --mail-user=abha4861@colorado.edu

set -eo pipefail  # no -u: ~/.myrc and conda activate reference unset vars
source ~/.myrc

module load anaconda
conda activate translation

export OMP_NUM_THREADS=${SLURM_CPUS_PER_TASK:-1}
export HF_HOME=$TMP/huggingface          # CLIP, shared cache
export TESSDATA_PREFIX=$TMP/tessdata
export TOKENIZERS_PARALLELISM=false

# MAX_FILES may be empty; the script treats empty as "no limit".
python -m scripts.screen_site_crawl_images -max-files "$MAX_FILES"
