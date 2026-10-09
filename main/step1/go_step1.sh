#!/bin/bash
# Step 1 in one go: the inbound links of AI news, then the seeds and their raw text.
#   1. N_WORKERS English link workers (scripts/primary_sources.py -corpus en -step links: CC-NEWS -> the English
#      link tables, data/interim/primary_sources/links/)
#   2. N_WORKERS Chinese link workers (-corpus zh: the site crawls -> data/interim/primary_sources_zh/links/)
#   3. link_storms (scripts/slurm/link_storms.slurm): English and Chinese media storms about the same event, from
#      the storm pipelines' exports (scripts/go_media_storms.sh, CORPUS=zh) -> data/processed/storm_links.tsv;
#      fails harmlessly if an export is missing
#   4. once all are done, build_seeds (main/step1/build_seeds.slurm): the seed table (with the storms citing each
#      seed in each language, and the linked storm pairs sharing it), the seeds' raw text, a report; emails when done
# Every part skips work already done (link files per input file, seeds already fetched), so rerun it whenever new
# CC-NEWS or crawl data has arrived. Run from the repo root.
#
# Usage:
#   bash main/step1/go_step1.sh
#   N_WORKERS=50 MIN_OUTLETS=10 bash main/step1/go_step1.sh

set -eo pipefail  # no -u: ~/.myrc references unset vars
source ~/.myrc
mkdir -p logs/scripts/slurm
N_WORKERS=${N_WORKERS:-100}

ids=""
for corpus in en zh; do
    for ((i = 0; i < N_WORKERS; i++)); do
        ids+=":$(sbatch --parsable --export="STEP=links,CORPUS=$corpus,MAX_FILES=" scripts/slurm/primary_sources.slurm)"
        sleep 0.2
    done
    echo "link workers ($corpus): $N_WORKERS"
done
LINKS=$(sbatch --parsable scripts/slurm/link_storms.slurm)
echo "link_storms $LINKS"
ids+=":$LINKS"
SEEDS=$(sbatch --parsable --dependency="afterany$ids" --export="MIN_OUTLETS=${MIN_OUTLETS:-5}" \
    main/step1/build_seeds.slurm)
echo "build_seeds $SEEDS, after all link workers (emails when done)"
echo
echo "Spot checks:"
echo "  squeue -u \$USER --name=primary_sources,link_storms,build_seeds -h -o '%j %T' | sort | uniq -c"
echo "  ls data/interim/primary_sources/links | wc -l; ls data/interim/primary_sources_zh/links | wc -l   # link files"
echo "  tail -30 logs/scripts/slurm/link_storms_$LINKS.out      # linked English-Chinese storms"
echo "  tail -60 logs/scripts/slurm/build_seeds_$SEEDS.out      # the seed report (with the storm crossings)"
