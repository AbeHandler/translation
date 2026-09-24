#!/bin/bash
# Driver for the whole site-crawl pipeline: one round of every step, submitted to SLURM with dependencies,
# returns right away. Every step skips work already done, so rerunning it runs the next round.
#   update_env         create/update the translation conda env (config/requirements.txt)
#   crawl_site         one job per site in config/sites.txt not yet done (scrapy/crawl_sites.sh). Each crawls
#                      for up to 23.5h, resuming where the last round stopped; writes pages.jsonl + html/*.parquet
#   embed_site_crawls  N_WORKERS CPU workers, after every crawl ends: bge-base-zh embeddings for each HTML file
#                      without them (scripts/embed_site_crawls.sh)
#   build_annoy_index  after every embed worker ends: rebuilds one Annoy index over all embeddings, replacing
#                      the old one (scripts/slurm/build_annoy_index.slurm)
# Each step also runs on its own (see its script). Clean slate: bash scrapy/flush_crawls.sh
# Outputs: data/interim/site_crawls/<domain>/{pages.jsonl,html/,embeddings/}, data/processed/site_crawls_annoy/
# Logs: logs/scrapy/, logs/scripts/slurm/. Run from the repo root.
#
# Usage:
#   bash scripts/site_crawls_go.sh
#   N_WORKERS=20 bash scripts/site_crawls_go.sh
#   MAX_PAGES=50 N_WORKERS=1 bash scripts/site_crawls_go.sh   # test: 50 pages per site

set -eo pipefail  # no -u: ~/.myrc references unset vars
source ~/.myrc
mkdir -p logs/scripts/slurm  # SLURM won't create the --output dir

# --export=NONE: don't inherit the login node's modules (see scripts/go.sh)
ENV_JOB=$(sbatch --parsable --export=NONE scripts/slurm/update_env.slurm)
echo "update_env         $ENV_JOB"

# afterany from here on: a crawl stopping on its time limit, or one failed site, shouldn't block the rest
CRAWL_JOBS=$(DEPENDENCY=afterok:$ENV_JOB bash scrapy/crawl_sites.sh | tee /dev/stderr | sed -n 's/^JOB_IDS=//p')
AFTER_CRAWLS=afterok:$ENV_JOB
if [ -n "$CRAWL_JOBS" ]; then AFTER_CRAWLS=afterany:$CRAWL_JOBS; fi

EMBED_JOBS=$(DEPENDENCY=$AFTER_CRAWLS bash scripts/embed_site_crawls.sh | tee /dev/stderr | sed -n 's/^JOB_IDS=//p')

INDEX_JOB=$(sbatch --parsable --export=NONE --dependency=afterany:"$EMBED_JOBS" scripts/slurm/build_annoy_index.slurm)
echo "build_annoy_index  $INDEX_JOB (after all embed workers)"

echo
echo "Spot checks:"
echo "  squeue -u \$USER --name=update_env,crawl_site,embed_site_crawls,build_annoy_index"
echo "  cat data/processed/site_crawls_annoy/info.json   # once build_annoy_index is done"
echo "  tail -30 logs/scripts/slurm/build_annoy_index_$INDEX_JOB.out   # neighbours of random pages"
