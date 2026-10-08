#!/bin/bash
# Download a Chinese font (Noto Sans SC, Regular and Bold; SIL Open Font License) to data/external/fonts, for plots
# with Chinese labels on machines without one (Alpine). Plots use any .ttf/.otf there first (src/fightin/plot.py).
# Rerun: skips fonts already there.
#   bash scripts/fetch_cjk_font.sh          (on a login node: needs internet)
set -eo pipefail
DIR=data/external/fonts
mkdir -p "$DIR"
for WEIGHT in Regular Bold; do
    FONT=$DIR/NotoSansSC-$WEIGHT.otf
    if [ -s "$FONT" ]; then
        echo "$FONT exists"
        continue
    fi
    curl -sSL -o "$FONT.part" "https://github.com/notofonts/noto-cjk/raw/main/Sans/SubsetOTF/SC/NotoSansSC-$WEIGHT.otf"
    mv "$FONT.part" "$FONT"
    ls -la "$FONT"
done
