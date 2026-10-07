#!/bin/bash
# Step 2 in one go: the seeds' salience in English and Chinese news (main/step2/seed_citations.py).
#   1. N_WORKERS citations workers: every article that links a seed (step 1's link tables), with its text and the
#      passages it quotes verbatim from the seed -> data/interim/step2/
#   2. once they are done, salience: -> data/processed/seed_citations.parquet, seed_quotes.parquet (passage, seed,
#      citing article, ...), seed_salience.tsv (one row per seed); emails when done
# Needs step 1 (data/processed/seeds.tsv and the seeds' texts in primary.pq). Files already done are skipped; after
# a new step 1, FLUSH=1 starts step 2 over (the seeds may have changed). Run from the repo root.
#
# Usage:
#   bash main/step2/go_step2.sh
#   FLUSH=1 bash main/step2/go_step2.sh
#   N_WORKERS=1 MAX_FILES=1 bash main/step2/go_step2.sh      # test

set -eo pipefail  # no -u: ~/.myrc references unset vars
source ~/.myrc
mkdir -p logs/scripts/slurm
N_WORKERS=${N_WORKERS:-100}

if [[ -n $FLUSH && -d data/interim/step2 ]]; then   # WARNING: deletes step 2's work files
    echo "flushing data/interim/step2"
    find data/interim/step2 -type f | shuf | xargs -r rm -f
fi
ids=""
for ((i = 0; i < N_WORKERS; i++)); do
    ids+=":$(sbatch --parsable --export="STEP=citations,MAX_FILES=$MAX_FILES" main/step2/seed_citations.slurm)"
    sleep 0.2
done
SALIENCE=$(sbatch --parsable --dependency="afterany$ids" --mem=64G --mail-type=END,FAIL \
    --export="STEP=salience,MAX_FILES=" main/step2/seed_citations.slurm)
echo "seed_citations: $N_WORKERS citations workers, then salience $SALIENCE (emails when done)"
echo
echo "Spot checks:"
echo "  ls data/interim/step2/citations | wc -l     # link-table files done"
echo "  tail -20 logs/scripts/slurm/seed_citations_$SALIENCE.out      # the salience summary"
