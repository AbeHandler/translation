#!/bin/bash
# Embed the pages the scrapy crawls saved: submits update_env, then N_WORKERS copies of
# scripts/slurm/embed_site_crawls.slurm. Each embeds HTML files that have no embeddings file yet
# (data/interim/site_crawls/<domain>/html/X.parquet -> <domain>/embeddings/X.parquet), so rerun it
# while the crawls are still writing to embed the new files.
#
# Usage (from the repo root):
#   bash scripts/embed_site_crawls.sh
#   N_WORKERS=20 bash scripts/embed_site_crawls.sh
#   N_WORKERS=1 MAX_FILES=1 bash scripts/embed_site_crawls.sh   # test

set -eo pipefail  # no -u: ~/.myrc references unset vars
source ~/.myrc

if [ -z "${TMP:-}" ]; then
    echo "ERROR: \$TMP is not set; the Hugging Face model cache goes in \$TMP/huggingface"
    exit 1
fi
N_WORKERS=${N_WORKERS:-10}
mkdir -p logs/scripts/slurm  # SLURM won't create the --output dir

# --export=NONE: don't inherit the login node's modules (see scripts/go.sh)
ENV_JOB=$(sbatch --parsable --export=NONE scripts/slurm/update_env.slurm)
echo "update_env         $ENV_JOB"

for i in $(seq 1 "$N_WORKERS"); do
    sbatch --parsable --dependency=afterok:"$ENV_JOB" --kill-on-invalid-dep=yes \
        --export="TMP=$TMP,MAX_FILES=$MAX_FILES" scripts/slurm/embed_site_crawls.slurm >/dev/null
done
echo "embed_site_crawls  $N_WORKERS workers (after $ENV_JOB)"

echo
echo "Spot checks:"
echo "  squeue -u \$USER --name=update_env,embed_site_crawls"
echo "  ls data/interim/site_crawls/*/html/*.parquet | wc -l; ls data/interim/site_crawls/*/embeddings/*.parquet | wc -l"
echo "  grep -h 'embedded /' logs/scripts/slurm/embed_site_crawls_*.out | tail"
