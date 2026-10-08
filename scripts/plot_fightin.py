#!/usr/bin/env python
"""
Redraw the Fightin' Words funnel plot from a fightin.tsv (scripts/fightin.py), e.g. on a laptop that has a Chinese
font, without the rest of the pipeline's dependencies (pandas and matplotlib only). Fonts in data/external/fonts are
used first (bash scripts/fetch_cjk_font.sh).

Run as a module from the repo root:
    python -m scripts.plot_fightin -tsv /tmp/fightin/fightin.tsv          # -> /tmp/fightin/funnel.png
"""
import argparse
import os

from config.paths import FONTS_DIR
from src.fightin.plot import funnel_plot_tsv


def parse_args():
    parser = argparse.ArgumentParser(description="Redraw a Fightin' Words funnel plot from fightin.tsv")
    parser.add_argument('-tsv', required=True)
    parser.add_argument('-png', default=None, help='default: funnel.png next to the tsv')
    parser.add_argument('-title', default="Fightin' Words: English vs Chinese AI")
    args = parser.parse_args()
    args.png = args.png or os.path.join(os.path.dirname(args.tsv), 'funnel.png')
    return args


def main():
    args = parse_args()
    funnel_plot_tsv(args.tsv, args.png, args.title, font_paths=sorted(FONTS_DIR.glob('*.[ot]tf')))
    print(f'-> {args.png}')


if __name__ == '__main__':
    main()
