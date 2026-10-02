#!/bin/bash
# Media storms over the embedded and dated English CC-NEWS articles (scripts/media_storms.py): N_WORKERS by_day
# workers, then N_WORKERS edges workers, then one cluster job and one storms job, each waiting for the last.
# Rerun after more WARCs are embedded and dated: only new WARCs are split; days that already have edges are kept
# (REDO_EDGES=1 recomputes them, which new articles on old days need). Run from the repo root.
#
# Usage:
#   bash scripts/go_media_storms.sh                 # 100 workers per step
#   N_WORKERS=1 MAX_FILES=1 bash scripts/go_media_storms.sh   # test

set -eo pipefail  # no -u: ~/.myrc references unset vars
source ~/.myrc
mkdir -p logs/scripts/slurm
N_WORKERS=${N_WORKERS:-100}

workers() {   # workers <step> <dependency or ''> <cpus> <mem>: prints :id:id...
    local ids=""
    for ((i = 0; i < N_WORKERS; i++)); do
        ids+=":$(sbatch --parsable ${2:+--dependency=$2} --job-name="media_storms_$1" --cpus-per-task="$3" --mem="$4" \
            --export="STEP=$1,MAX_FILES=$MAX_FILES,REDO_EDGES=$REDO_EDGES" scripts/slurm/media_storms.slurm)"
    done
    echo "$ids"
}
BY_DAY=$(workers by_day "" 1 8G)
EDGES=$(workers edges "afterany$BY_DAY" 8 32G)
CLUSTER=$(sbatch --parsable --dependency="afterany$EDGES" --job-name=media_storms_cluster --cpus-per-task=1 --mem=64G \
    --time=08:00:00 --export="STEP=cluster" scripts/slurm/media_storms.slurm)
STORMS=$(sbatch --parsable --dependency="afterok:$CLUSTER" --job-name=media_storms_storms --cpus-per-task=1 --mem=64G \
    --time=08:00:00 --mail-type=END,FAIL --export="STEP=storms" scripts/slurm/media_storms.slurm)
echo "media_storms: $N_WORKERS by_day, then $N_WORKERS edges, then cluster $CLUSTER, then storms $STORMS"
echo
echo "Spot checks:"
echo "  squeue -u \$USER -o '%j %T' | grep media_storms | sort | uniq -c"
echo "  ls data/interim/media_storms/edges | wc -l              # days with edges"
echo "  tail -25 \$(ls -t logs/scripts/slurm/media_storms_storms_*.out | head -1)   # the storms, largest first"
