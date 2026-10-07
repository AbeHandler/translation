#!/bin/bash
# Step 3 in one go: which seeds cross into Chinese news (main/step3/crossings.py), each part after the last:
#   1. N_WORKERS embed_zh workers: the Chinese AI pages of the crawls, LaBSE vectors (data/interim/step3/zh/);
#      and, alongside, the screenshots step (the English screenshots matched against the seeds)
#   2. N_WORKERS candidates workers: per seed, the most similar Chinese pages in its window, scored sentence by
#      sentence (data/interim/step3/candidates/)
#   3. table: every (seed, Chinese article) pair with any evidence (link, screenshot, English quote, similarity)
#   4. fit: model1 -> data/processed/seed_crossings.parquet (P(crossed) per pair), seed_transmission.tsv (per
#      seed); emails when done
# Needs steps 1 and 2. Workers skip what is done; after a new step 1, FLUSH=1 redoes the candidates (the seeds may
# have changed; the Chinese vectors are kept). Run from the repo root.
#
# Usage:
#   bash main/step3/go_step3.sh
#   N_WORKERS=50 bash main/step3/go_step3.sh
#   FLUSH=1 bash main/step3/go_step3.sh

set -eo pipefail  # no -u: ~/.myrc references unset vars
source ~/.myrc
mkdir -p logs/scripts/slurm
N_WORKERS=${N_WORKERS:-100}

if [[ -n $FLUSH && -d data/interim/step3/candidates ]]; then   # WARNING: deletes the candidates (not the vectors)
    echo "flushing data/interim/step3/candidates"
    find data/interim/step3/candidates -type f | shuf | xargs -r rm -f
fi
workers() {   # workers <step> <dependency ids>: prints :id:id...
    local ids=""
    for ((i = 0; i < N_WORKERS; i++)); do
        ids+=":$(sbatch --parsable ${2:+--dependency=afterany$2} --export="STEP=$1,MAX_FILES=$MAX_FILES" \
            main/step3/crossings.slurm)"
        sleep 0.2
    done
    echo "$ids"
}
one() {       # one <step> <dependency ids> [sbatch options]: prints :id
    echo ":$(sbatch --parsable ${2:+--dependency=afterany$2} "${@:3}" --export="STEP=$1,MAX_FILES=" \
        main/step3/crossings.slurm)"
}
EMBED=$(workers embed_zh "")
SHOTS=$(one screenshots "")
CANDIDATES=$(workers candidates "$EMBED")
TABLE=$(one table "$CANDIDATES$SHOTS")
FIT=$(one fit "$TABLE" --mail-type=END,FAIL)
echo "crossings: $N_WORKERS embed_zh workers + screenshots, then $N_WORKERS candidates workers, then table, then fit ${FIT#:} (emails when done)"
echo
echo "Spot checks:"
echo "  ls data/interim/step3/zh | wc -l; ls data/interim/step3/candidates | wc -l"
echo "  tail -30 logs/scripts/slurm/crossings_${FIT#:}.out      # crossing per seed and what the evidence says"
