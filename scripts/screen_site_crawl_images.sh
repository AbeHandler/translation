#!/bin/bash
# Screen the Chinese site crawls' AI articles for English screenshots (scripts/screen_site_crawl_images.py):
# N_WORKERS workers sharing the crawls' HTML files; files already screened are skipped, so rerun it as the
# crawls write more. Run from the repo root; run scripts/slurm/update_env.slurm once first (Tesseract).
#
# Usage:
#   bash scripts/screen_site_crawl_images.sh                          # 50 workers
#   N_WORKERS=1 MAX_FILES=1 bash scripts/screen_site_crawl_images.sh  # test: one HTML file

set -eo pipefail  # no -u: ~/.myrc references unset vars
source ~/.myrc
mkdir -p logs/scripts/slurm
N_WORKERS=${N_WORKERS:-50}
for ((i = 0; i < N_WORKERS; i++)); do
    sbatch --parsable --export="MAX_FILES=$MAX_FILES" scripts/slurm/screen_site_crawl_images.slurm > /dev/null
done
echo "screen_site_crawl_images  $N_WORKERS workers"
echo
echo "Spot checks:"
echo "  ls data/interim/site_crawls/*/html/*.parquet | wc -l; ls data/interim/site_crawls/*/images/*.jsonl | wc -l"
echo "  grep -h 'done ' \$(ls -t logs/scripts/slurm/screen_site_crawl_images_*.out | head -3) | tail -3"
echo "  cat data/interim/site_crawls/*/images/*.jsonl | jq -c '.url as \$p | .images[] | select(.english_screenshot) | {page: \$p, src, ocr_text}' | head"
