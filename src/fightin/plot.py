"""The funnel plot of Fightin' Words (the paper's Figures 4-5): each word's z-score against its total frequency
(log scale), |z| < 1.96 in grey, significant words in their group's colour, the top words of each group labelled
and listed down the right side."""
import numpy as np

CJK_FONTS = ['Noto Sans CJK SC', 'Source Han Sans SC', 'WenQuanYi Zen Hei', 'SimHei', 'Arial Unicode MS',
             'DejaVu Sans']   # matplotlib falls back through these, so Chinese labels render where a font exists


def funnel_plot(labels, frequency, z, path, top=20, title='', groups=('i', 'j'), colors=('tab:blue', 'tab:red')):
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    plt.rcParams['font.sans-serif'] = CJK_FONTS
    labels, frequency, z = list(labels), np.asarray(frequency, float), np.asarray(z, float)
    significant = np.abs(z) >= 1.96
    size = 2 + 40 * np.abs(z) / max(np.abs(z).max(), 1e-9)
    fig, ax = plt.subplots(figsize=(11, 9))
    ax.scatter(frequency[~significant], z[~significant], s=size[~significant], c='lightgrey', lw=0)
    for side, color in zip((z >= 1.96, z <= -1.96), colors):
        ax.scatter(frequency[side], z[side], s=size[side], c=color, lw=0)
    order = np.argsort(z)
    top_i, top_j = order[::-1][:top], order[:top]
    for ks, color in ((top_i, colors[0]), (top_j, colors[1])):
        for k in ks:
            ax.annotate(labels[k], (frequency[k], z[k]), fontsize=7, xytext=(3, 0), textcoords='offset points',
                        color=color)
    fig.text(0.83, 0.88, f'{groups[0]}\n' + '\n'.join(labels[k] for k in top_i), fontsize=7, va='top', color=colors[0])
    fig.text(0.83, 0.48, f'{groups[1]}\n' + '\n'.join(labels[k] for k in top_j[::-1]), fontsize=7, va='top',
             color=colors[1])
    ax.set_xscale('log')
    ax.axhline(0, c='grey', lw=0.5)
    ax.set_xlabel('Frequency of word (both groups)')
    ax.set_ylabel(f'z-score of log-odds-ratio ({groups[0]} up, {groups[1]} down)')
    ax.set_title(title)
    fig.subplots_adjust(right=0.8)
    fig.savefig(path, dpi=150)
    plt.close(fig)
