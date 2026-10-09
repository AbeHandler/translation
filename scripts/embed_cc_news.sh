#!/bin/bash
# Embed the English CC-NEWS articles about AI for media-storm clustering (scripts/embed_cc_news.py): one job that
# downloads the news-similarity model (once), then N_WORKERS workers sharing the WARCs. Rerun any time: WARCs
# with an embeddings file are skipped. Run from the repo root.
#
# Usage:
#   bash scripts/embed_cc_news.sh                         # 100 workers
#   N_WORKERS=200 bash scripts/embed_cc_news.sh
#   N_WORKERS=1 MAX_FILES=1 bash scripts/embed_cc_news.sh # test: one WARC
#   DEPENDENCY=afterany:<id>:<id> bash scripts/embed_cc_news.sh   # workers wait for those jobs (main/step0/go_step0.sh)
# Last line printed: JOB_IDS=<id>:<id>..., for chaining.

set -eo pipefail  # no -u: ~/.myrc references unset vars
source ~/.myrc
mkdir -p logs/scripts/slurm
N_WORKERS=${N_WORKERS:-100}

DOWNLOAD_JOB=$(sbatch --parsable --export=DOWNLOAD_ONLY=1 --time=01:00:00 scripts/slurm/embed_cc_news.slurm)
echo "embed_cc_news download  $DOWNLOAD_JOB (the model, once)"
JOB_IDS=""
for ((i = 0; i < N_WORKERS; i++)); do
    JOB_IDS+=":$(sbatch --parsable --dependency=afterok:"$DOWNLOAD_JOB"${DEPENDENCY:+,$DEPENDENCY} --kill-on-invalid-dep=yes \
        --export="MAX_FILES=$MAX_FILES" scripts/slurm/embed_cc_news.slurm)"
done
echo "embed_cc_news           $N_WORKERS workers after it${DEPENDENCY:+ and $DEPENDENCY}"
echo
echo "Spot checks:"
echo "  squeue -u \$USER --name=embed_cc_news | wc -l"
echo "  ls data/interim/cc_news_embeddings | grep -c 'parquet\$'      # WARCs done (of ~21.7k)"
echo "  grep -h 'done ' \$(ls -t logs/scripts/slurm/embed_cc_news_*.out | head -3) | tail -3   # articles and seconds per WARC"
echo "JOB_IDS=${JOB_IDS#:}"   # for launchers that chain after the workers
