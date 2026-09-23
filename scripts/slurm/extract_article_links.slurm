#!/bin/bash
# Worker for src/cc_news.py -step extract_article_links: shuffles $TMP/warcs/todo.txt and processes each WARC not
# done or locked by another worker. scripts/find_seed_links_go.sh submits N of these after update_env and write_warc_todo.
#
# Usage (from the repo root; normally via scripts/find_seed_links_go.sh):
#   sbatch --export=AWS=/home/abha4861/bin/v2/2.5.4/bin/aws,TMP=$TMP scripts/slurm/extract_article_links.slurm
#   optional: MAX_N=100, MAX_WARCS=1, OUTPUT_DIR=data/interim/cc_links

#SBATCH --partition=acpu
#SBATCH --time=24:00:00
#SBATCH --job-name=extract_article_links
#SBATCH --mem=8G
#SBATCH --qos=normal
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --mail-type=FAIL
#SBATCH --mail-user=abha4861@colorado.edu

set -eo pipefail  # no -u: ~/.myrc and conda activate reference unset vars
source ~/.myrc  # first, so $TMP etc. from ~/.myrc are set before the checks below

if [ -z "${AWS:-}" ] || [ -z "${TMP:-}" ]; then
    echo "ERROR: AWS (path to aws CLI) and TMP (.lock/.done files go in \$TMP/warcs) are required"
    echo "Usage: sbatch --export=AWS=/home/abha4861/bin/v2/2.5.4/bin/aws,TMP=\$TMP scripts/slurm/extract_article_links.slurm"
    exit 1
fi

module load anaconda
conda activate translation

# Optional vars may be empty; src/cc_news.py treats empty as "use the default".
python src/cc_news.py \
    -step extract_article_links \
    -aws "$AWS" \
    -work-dir "$TMP/warcs" \
    -max-n "$MAX_N" \
    -max-warcs "$MAX_WARCS" \
    -output-dir "$OUTPUT_DIR"
