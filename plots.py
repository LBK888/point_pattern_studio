"""L(r) plot (Ripley's L function) rendered with matplotlib's Agg canvas.

Only the object-oriented API is used (no pyplot), so plots can be drawn from
worker threads and from the command line without a display.
All plot text is English. A CJK font is only used as a fallback, so a Chinese
file name in an import title still renders.
"""
from __future__ import annotations

import csv
import io
from functools import lru_cache
from pathlib import Path

import numpy as np
from matplotlib import font_manager
from matplotlib.backends.backend_agg import FigureCanvasAgg
from matplotlib.figure import Figure
from matplotlib.font_manager import FontProperties
from matplotlib.ticker import FormatStrFormatter, MultipleLocator

from point_core import (RADII_FACTORS, CSR_ENVELOPE_SIMS, l_axis_limit, l_curve_for_plot,
                        csr_l_envelope, l_curve_summary)

_CJK_FONTS = ('Microsoft JhengHei', 'Microsoft YaHei', 'PingFang TC', 'Heiti TC', 'Hiragino Sans',
              'Noto Sans CJK TC', 'Noto Sans TC', 'Source Han Sans TC', 'Arial Unicode MS', 'SimHei')


@lru_cache(maxsize=1)
def cjk_font():
    """First installed font that can show Chinese, or None."""
    names = {f.name for f in font_manager.fontManager.ttflist}
    return next((f for f in _CJK_FONTS if f in names), None)


def plot_title(name, score):
    """Two-line title: what the pattern is, then its score."""
    return f'{name}\nscore = {score:+.3f}'


def l_plot_png(curve, envelope=None, title='', path=None, sims=39, dpi=150):
    """Draw L(r) with the 45-degree CSR line on square axes (same range and ticks on x and y).
    Return PNG bytes, and also save to `path` if given.

    curve: dict from point_core.l_curve_for_plot (or ripley_l_curve);
    envelope: (low, high) arrays on the same r grid, or None.
    """
    cjk = cjk_font()
    fp = FontProperties(family=['DejaVu Sans'] + ([cjk] if cjk else []))
    small = fp.copy(); small.set_size(8.5)
    r, L = np.asarray(curve['r']), np.asarray(curve['l'])
    top, step = curve.get('axis_max'), curve.get('tick_step')
    if top is None:
        top, step = l_axis_limit(float(L.max()), float(r[-1]))

    fig = Figure(figsize=(5.4, 5.4), dpi=dpi, facecolor='white')
    FigureCanvasAgg(fig)
    ax = fig.add_subplot(111)
    spacing = curve.get('spacing')
    if spacing:
        lo_s, hi_s = RADII_FACTORS[0] * spacing, RADII_FACTORS[-1] * spacing
        if lo_s < top:
            ax.axvspan(lo_s, min(hi_s, top), color='#f2c14e', alpha=.16, lw=0, label='r range used by the score')
    if envelope is not None:
        ax.fill_between(r, envelope[0], envelope[1], color='#b8c4cc', alpha=.55, lw=0,
                        label=f'CSR envelope ({sims} simulations)')
    ax.plot([0, top], [0, top], ls=(0, (5, 4)), color='#3d4a52', lw=1.4, label='CSR: L(r) = r')
    ax.plot(r, L, color='#146c88', lw=2.3, label='observed L(r)')
    # Same limits and ticks on both axes + equal scaling: a square plot whose
    # diagonal is the 45-degree line L(r) = r.
    ax.set_xlim(0, top)
    ax.set_ylim(0, top)
    ax.set_aspect('equal', adjustable='box')
    decimals = max(2, len(f'{step:.10f}'.rstrip('0').split('.')[1]))
    for axis in (ax.xaxis, ax.yaxis):
        axis.set_major_locator(MultipleLocator(step))
        axis.set_major_formatter(FormatStrFormatter(f'%.{decimals}f'))
    ax.tick_params(labelsize=8.5)
    ax.grid(color='#e3e9ed', lw=.8)
    ax.set_axisbelow(True)
    for side in ('top', 'right'):
        ax.spines[side].set_visible(False)
    ax.set_xlabel('r (canvas height = 1)', fontproperties=fp)
    ax.set_ylabel('L(r)', fontproperties=fp)
    if title:
        ax.set_title(title, fontproperties=fp, fontsize=10.5, loc='left', linespacing=1.35)
    # The lower-right corner (large r, small L) is empty for every pattern type.
    ax.legend(loc='lower right', prop=small, framealpha=.92, edgecolor='#d5dde2')
    ax.text(.02, .98, 'above dashed line: clustered\nbelow dashed line: regular', transform=ax.transAxes,
            ha='left', va='top', fontproperties=small, color='#6b7a84', linespacing=1.4)
    fig.tight_layout()
    buf = io.BytesIO()
    fig.savefig(buf, format='png', dpi=dpi, facecolor='white')
    data = buf.getvalue()
    if path is not None:
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
    return data


def save_l_curves_csv(path, curves):
    """Long format, one row per (pattern, r): exactly the numbers drawn in each plot.

    curves: list of (name, curve, envelope_or_None)."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('w', newline='', encoding='utf-8-sig') as f:
        w = csv.writer(f)
        w.writerow(['pattern', 'r', 'L', 'L_minus_r', 'K', 'csr_envelope_low', 'csr_envelope_high'])
        for name, curve, env in curves:
            r, L, K = curve['r'], curve['l'], curve['k']
            for i in range(len(r)):
                lo, hi = (env[0][i], env[1][i]) if env is not None else (None, None)
                w.writerow([name] + ['' if v is None else f'{v:.9g}'
                                     for v in (r[i], L[i], L[i] - r[i], K[i], lo, hi)])


def l_analysis(points, aspect, title='', path=None):
    """Everything the L(r) panel needs for one point set:
    (curve, CSR envelope, summary numbers, PNG bytes)."""
    curve = l_curve_for_plot(points, aspect)
    envelope = csr_l_envelope(curve['n'], aspect, curve['r'])
    summary = l_curve_summary(curve, envelope)
    png = l_plot_png(curve, envelope, title, path, CSR_ENVELOPE_SIMS)
    return curve, envelope, summary, png
