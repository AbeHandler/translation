#!/bin/bash
# Download a Chinese font (Noto Sans SC, SIL Open Font License) to data/external/fonts, for plots with Chinese
# labels on machines without one (Alpine). Plots use any .ttf/.otf there first (src/fightin/plot.py). Rerun: skips.
#   bash scripts/fetch_cjk_font.sh          (on a login node: needs internet)
set -eo pipefail
DIR=data/external/fonts
FONT=$DIR/NotoSansSC-Regular.otf
mkdir -p "$DIR"
if [ -s "$FONT" ]; then
    echo "$FONT exists"
    exit 0
fi
curl -sSL -o "$FONT.part" "https://github.com/notofonts/noto-cjk/raw/main/Sans/SubsetOTF/SC/NotoSansSC-Regular.otf"
mv "$FONT.part" "$FONT"
ls -la "$FONT"
