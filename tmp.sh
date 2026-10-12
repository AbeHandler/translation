#!/bin/bash
# Check the Chinese storms after the by_day re-split: the gold-list traces (where the OpenAI/Hugging Face and
# DeepSeek-R1 articles are lost) and the storm funnel.
#   bash tmp.sh        (from the repo root, on Alpine, after git pull)
set -eo pipefail
mkdir -p logs/scripts/slurm
A=$(sbatch --parsable --export=GOLD=config/gold/chinese_coverage_hf_openai_anthropic.csv scripts/slurm/check_gold_coverage.slurm)
B=$(sbatch --parsable --export=GOLD=config/gold/chinese_coverage_deepseek_r1.csv scripts/slurm/check_gold_coverage.slurm)
C=$(sbatch --parsable debug.slurm)
echo "check_gold_coverage $A (OpenAI/HF), $B (DeepSeek-R1); debug $C"
echo
echo "When done (squeue -u \$USER --name=check_gold_coverage,debug is empty):"
echo "  cat logs/scripts/slurm/debug_$C.out | head -60"
echo "  tail -14 logs/scripts/slurm/check_gold_coverage_$A.out"
echo "  tail -14 logs/scripts/slurm/check_gold_coverage_$B.out"
