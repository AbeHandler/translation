#!/bin/bash
# Primary sources from the links in AI news (scripts/primary_sources.py): N_WORKERS links workers, then the sources
# step (emails when done). CORPUS=en (default): English CC-NEWS -> data/processed/primary_sources.tsv;
# CORPUS=zh: the Chinese site crawls -> data/processed/primary_sources_zh.tsv. Files already done are skipped,
# so rerun as the corpora grow. Run from the repo root.
#
# Usage:
#   bash scripts/go_primary_sources.sh
#   CORPUS=zh bash scripts/go_primary_sources.sh     # the Chinese side
#   FLUSH=1 bash scripts/go_primary_sources.sh       # first delete that corpus's link tables (a clean run)
#   N_WORKERS=1 MAX_FILES=1 bash scripts/go_primary_sources.sh   # test

set -eo pipefail  # no -u: ~/.myrc references unset vars
source ~/.myrc
mkdir -p logs/scripts/slurm
N_WORKERS=${N_WORKERS:-100}
CORPUS=${CORPUS:-en}

dep=""
if [[ -n $FLUSH ]]; then
    dep=":$(sbatch --parsable --export=STEP=flush,CORPUS=$CORPUS scripts/slurm/primary_sources.slurm)"
fi
ids=""
for ((i = 0; i < N_WORKERS; i++)); do
    ids+=":$(sbatch --parsable ${dep:+--dependency=afterok$dep} --export="STEP=links,CORPUS=$CORPUS,MAX_FILES=$MAX_FILES" \
        scripts/slurm/primary_sources.slurm)"
done
SOURCES=$(sbatch --parsable --dependency="afterany$ids" --mem=64G --mail-type=END,FAIL --export=STEP=sources,CORPUS=$CORPUS \
    scripts/slurm/primary_sources.slurm)
echo "primary_sources ($CORPUS): $N_WORKERS links workers, then sources $SOURCES (emails when done)"
echo
echo "Spot checks:"
echo "  squeue -u \$USER --name=primary_sources | wc -l"
echo "  ls data/interim/primary_sources$([ $CORPUS = zh ] && echo _zh)/links | wc -l      # files done"
echo "  tail -30 logs/scripts/slurm/primary_sources_$SOURCES.out"
