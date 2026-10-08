"""The funnel plot of Fightin' Words (the paper's Figures 4-5): each word's z-score against its total frequency
(log scale), |z| < 1.96 in grey, significant words in their group's colour, the top words of each group numbered
and listed in a table beside the plot (word, Chinese form, z)."""
import re

import numpy as np

CJK = re.compile('[\u4e00-\u9fff]')

CJK_FONTS = ['Noto Sans CJK SC', 'Source Han Sans SC', 'WenQuanYi Zen Hei', 'SimHei', 'Arial Unicode MS',
             'DejaVu Sans']   # matplotlib falls back through these, so Chinese labels render where a font exists


def use_fonts(font_paths=()):
    """Register extra font files (e.g. Noto Sans SC, for machines without a Chinese font) and put them first."""
    import matplotlib
    matplotlib.use('Agg')
    from matplotlib import font_manager
    import matplotlib.pyplot as plt
    names = []
    for p in font_paths:
        font_manager.fontManager.addfont(str(p))
        names.append(font_manager.FontProperties(fname=str(p)).get_name())
    plt.rcParams['font.sans-serif'] = names + CJK_FONTS


def chinese_form(forms):
    """The first Chinese word of a space-separated list of a concept's forms ('' if none is Chinese)."""
    return next((f for f in str(forms).split() if CJK.search(f)), '')


def funnel_plot(words, frequency, z, path, chinese=None, top=20, title='', groups=('i', 'j'),
                colors=('tab:blue', 'tab:red'), font_paths=()):
    """Points numbered by rank on each side; a table beside the plot gives each rank's word, its Chinese form
    (chinese: one per word, optional) and z."""
    use_fonts(font_paths)
    import matplotlib.pyplot as plt
    words, frequency, z = list(words), np.asarray(frequency, float), np.asarray(z, float)
    chinese = list(chinese) if chinese is not None else [''] * len(words)
    significant = np.abs(z) >= 1.96
    size = 2 + 40 * np.abs(z) / max(np.abs(z).max(), 1e-9)
    fig, (ax, table) = plt.subplots(1, 2, figsize=(15, 9), gridspec_kw={'width_ratios': [3, 1.1], 'wspace': 0.05})
    ax.scatter(frequency[~significant], z[~significant], s=size[~significant], c='lightgrey', lw=0)
    for side, color in zip((z >= 1.96, z <= -1.96), colors):
        ax.scatter(frequency[side], z[side], s=size[side], c=color, lw=0)
    order = np.argsort(z)
    sides = [([k for k in order[::-1][:top] if z[k] > 0], groups[0], colors[0]),   # each side: its own words only
             ([k for k in order[:top] if z[k] < 0], groups[1], colors[1])]
    table.axis('off')
    row, step = 1.0, 1.0 / (2 * top + 4)
    for ranked, name, color in sides:
        table.text(0, row, f'Most {name}', color=color, fontsize=10, fontweight='bold', va='top')
        row -= step
        for rank, k in enumerate(ranked, 1):
            ax.annotate(str(rank), (frequency[k], z[k]), fontsize=7, xytext=(3, 2), textcoords='offset points',
                        color=color, fontweight='bold')
            for x, text, align in ((0.0, f'{rank}.', 'left'), (0.1, words[k], 'left'), (0.6, chinese[k], 'left'),
                                   (1.0, f'{z[k]:.1f}', 'right')):
                table.text(x, row, text, color=color, fontsize=9, va='top', ha=align)
            row -= step
        row -= step
    ax.set_xscale('log')
    ax.axhline(0, c='grey', lw=0.5)
    ax.set_xlabel('Frequency of word (both groups)')
    ax.set_ylabel(f'z-score of log-odds-ratio ({groups[0]} up, {groups[1]} down)')
    ax.set_title(title)
    fig.savefig(path, dpi=150, bbox_inches='tight')
    plt.close(fig)


def funnel_plot_tsv(tsv, png, title='', font_paths=()):
    """The funnel plot of a fightin.tsv (scripts/fightin.py: concept, zh_forms, en, zh, z): English blue, Chinese
    red."""
    import pandas as pd
    table = pd.read_csv(tsv, sep='\t', keep_default_na=False)
    funnel_plot(table['concept'], table['en'] + table['zh'], table['z'], png,
                chinese=table['zh_forms'].map(chinese_form), groups=('English', 'Chinese'),
                colors=('tab:blue', 'tab:red'), title=title, font_paths=font_paths)
