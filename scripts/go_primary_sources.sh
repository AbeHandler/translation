#!/bin/bash
# Primary sources from the links in AI news (scripts/primary_sources.py): N_WORKERS links workers over the English
# CC-NEWS links files and the Chinese crawl links, then the sources step -> data/processed/primary_sources.tsv
# (emails when done). Files already done are skipped, so rerun as the corpora grow. Run from the repo root.
#
# Usage:
#   bash scripts/go_primary_sources.sh
#   FLUSH=1 bash scripts/go_primary_sources.sh       # first delete data/interim/primary_sources (a clean run)
#   N_WORKERS=1 MAX_FILES=1 bash scripts/go_primary_sources.sh   # test

set -eo pipefail  # no -u: ~/.myrc references unset vars
source ~/.myrc
mkdir -p logs/scripts/slurm
N_WORKERS=${N_WORKERS:-100}

dep=""
if [[ -n $FLUSH ]]; then
    dep=":$(sbatch --parsable --export=STEP=flush scripts/slurm/primary_sources.slurm)"
fi
ids=""
for ((i = 0; i < N_WORKERS; i++)); do
    ids+=":$(sbatch --parsable ${dep:+--dependency=afterok$dep} --export="STEP=links,MAX_FILES=$MAX_FILES" \
        scripts/slurm/primary_sources.slurm)"
done
SOURCES=$(sbatch --parsable --dependency="afterany$ids" --mem=64G --mail-type=END,FAIL --export=STEP=sources \
    scripts/slurm/primary_sources.slurm)
echo "primary_sources: $N_WORKERS links workers, then sources $SOURCES (emails when done)"
echo
echo "Spot checks:"
echo "  squeue -u \$USER --name=primary_sources | wc -l"
echo "  ls data/interim/primary_sources/links | wc -l      # files done"
echo "  tail -30 logs/scripts/slurm/primary_sources_$SOURCES.out"
