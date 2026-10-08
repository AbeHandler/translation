#!/bin/bash
# Fightin' Words on context windows: for every selection with a pattern (config/fightin_selections.tsv; not "all"),
# only the words within WINDOW (default 200) words of a mention (Anthropic +/- 200 words), at 1k, 5k and 20k.
# Same samples as the whole-document runs (results/fightin/<selection>_<n>k/), outputs suffixed _w<WINDOW>
# (fightin_ngrams2-3_w200.tsv, funnel_ngrams2-3_w200.png). A job waits for any job of its experiment still running.
#   bash scripts/go_fightin_window.sh                  (from the repo root, on a login node)
#   bash scripts/go_fightin_window.sh anthropic openai # only these
#   WINDOW=100 bash scripts/go_fightin_window.sh
set -eo pipefail
SELECTIONS=${*:-$(grep -v '^#' config/fightin_selections.tsv | tail -n +2 | awk -F'\t' '$2 != "" {print $1}')}
WINDOW=${WINDOW:-200} bash scripts/go_fightin.sh $SELECTIONS
