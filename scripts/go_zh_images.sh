#!/bin/bash
# Screen the Chinese documents' images for English screenshots (src/clip.py): queue the documents, then N_WORKERS
# workers that wait for the queue (each image is fetched into memory, classified with CLIP, OCR'd if it may be a
# screenshot of text, and dropped), then the collect job -> data/processed/zh_images.jsonl: per document, its image
# URLs with class, OCR text and english_screenshot. Rerun after more documents are fetched: only new ones are
# screened. Needs Tesseract in the env (bash: sbatch --export=NONE scripts/slurm/update_env.slurm). Run from the
# repo root.
#
# Usage:
#   bash scripts/go_zh_images.sh                  # 50 workers
#   N_WORKERS=1 MAX_SHARDS=1 bash scripts/go_zh_images.sh    # test: one shard of 20 documents

set -eo pipefail  # no -u: ~/.myrc references unset vars
source ~/.myrc
mkdir -p logs/scripts/slurm

QUEUE_JOB=$(sbatch --parsable --export=NONE scripts/slurm/zh_images_queue.slurm)
echo "zh_images_queue $QUEUE_JOB"
N_WORKERS=${N_WORKERS:-50} DEPENDENCY=afterok:$QUEUE_JOB bash scripts/process_queue.sh zh_images
