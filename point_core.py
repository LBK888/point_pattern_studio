"""Point Pattern Studio: spatial statistics, raster I/O, image contour sampling and optimization.
All coordinates exposed in files are normalized to [0, 1] on each axis.
Statistics use an aspect-corrected rectangular observation window (width=aspect, height=1).
Scores are engineered statistical indices, NOT calibrated human ratings or p-values.
"""
from __future__ import annotations

import csv
import json
import math
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Callable

import cv2
import numpy as np
from PIL import Image, ImageOps
from scipy import ndimage
from scipy.spatial import cKDTree

RADII_FACTORS = np.array([0.50, 0.75, 1.00, 1.25, 1.50], dtype=float)
# Retain previous demonstration's fixed, non-human-calibrated Hopkins anchors.
H_CLUSTER_ANCHOR = 0.95
H_REGULAR_ANCHOR = 0.20
SCORE_HOPKINS_WEIGHT = 0.70
SCORE_RIPLEY_WEIGHT = 0.30
RIPLEY_SOFT_SCALE = 0.28
# Every analysis (all GUI tabs, CLI, optimizer) uses the same probe seed, so the
# score depends only on the point set and the canvas aspect ratio.
HOPKINS_PROBE_SEED = 2026
HOPKINS_MIN_PROBES = 2048


def load_image(path, mode='L') -> np.ndarray:
    """Read an image as 8-bit 'L' or 'RGB'.
    Transparent areas become white paper (otherwise PNG line art with a transparent
    background turns entirely black), and phone-photo EXIF rotation is applied.
    """
    with Image.open(path) as im:
        im = ImageOps.exif_transpose(im)
        if im.mode in ('I', 'F') or im.mode.startswith('I;16'):
            arr = np.asarray(im, dtype=float)
            lo, hi = float(arr.min()), float(arr.max())
            arr = (arr - lo) / (hi - lo) * 255 if hi > lo else np.full(arr.shape, 255.)
            im = Image.fromarray(arr.astype(np.uint8))
        elif im.mode in ('RGBA', 'LA', 'PA') or 'transparency' in im.info:
            rgba = im.convert('RGBA')
            paper = Image.new('RGBA', rgba.size, (255, 255, 255, 255))
            im = Image.alpha_composite(paper, rgba)
        return np.asarray(im.convert(mode))


def canvas_size(aspect=1.0, long_side=800):
    """Pixel size (w, h) whose long side is `long_side` and whose ratio is `aspect`."""
    if aspect >= 1:
        return int(long_side), max(1, int(round(long_side / aspect)))
    return max(1, int(round(long_side * aspect))), int(long_side)


def validate_points(points: np.ndarray, min_n: int = 3) -> np.ndarray:
    p = np.asarray(points, dtype=float)
    if p.ndim != 2 or p.shape[1] != 2 or len(p) < min_n:
        raise ValueError(f"需至少 {min_n} 個 (x,y) 座標。")
    if not np.all(np.isfinite(p)) or np.any(p < -1e-9) or np.any(p > 1+1e-9):
        raise ValueError("座標必須是 [0, 1] 範圍內的有限數值。")
    return np.clip(p, 0, 1)


def shape_points(points, aspect=1.0):
    if aspect <= 0 or not math.isfinite(aspect):
        raise ValueError("圖片寬高比必須大於零。")
    return np.asarray(points, dtype=float) * np.array([aspect, 1.0])


@dataclass
class HopkinsProbes:
    """Fixed stratified uniform probes for the empty-space part of Hopkins H.

    v1.0 sampled ~10% of the data points *by index* for the nearest-neighbour part.
    That made H depend on point order (the same pattern re-imported from PNG or
    shuffled could move the score by >0.1) and let the optimizer "hit" a target
    by moving only the sampled points. v1.1 uses every data point for that part,
    and a jittered-grid probe set for the empty-space part. The expected value of
    H is unchanged (ratio of mean squared distances); only sampling noise drops.
    """
    uniform: np.ndarray


def make_hopkins_probes(n: int, aspect=1.0, repeats=24, seed=HOPKINS_PROBE_SEED,
                        min_probes=HOPKINS_MIN_PROBES) -> HopkinsProbes:
    rng = np.random.default_rng(seed)
    m = max(3, min(n, int(math.ceil(n * .10))))
    count = max(int(min_probes), int(repeats) * m)
    gx = max(1, int(round(math.sqrt(count * aspect))))
    gy = max(1, int(math.ceil(count / gx)))
    ys, xs = np.mgrid[:gy, :gx]
    cells = np.column_stack((xs.ravel(), ys.ravel())).astype(float)
    # One uniform probe per cell: still uniform over the window, with less variance.
    uniform = (cells + rng.random(cells.shape)) / np.array([gx, gy]) * np.array([aspect, 1.0])
    return HopkinsProbes(uniform)


def hopkins(points, aspect=1., probes: HopkinsProbes | None = None):
    """H = mean(u²) / (mean(u²) + mean(w²)); u: probe→nearest point, w: point→nearest other point."""
    q = shape_points(validate_points(points), aspect)
    if probes is None:
        probes = make_hopkins_probes(len(q), aspect)
    tree = cKDTree(q)
    u2 = float(np.mean(tree.query(probes.uniform, workers=1)[0] ** 2))
    w2 = float(np.mean(tree.query(q, k=2, workers=1)[0][:, 1] ** 2))
    return float(u2 / (u2 + w2)) if u2 + w2 > 1e-15 else 0.5


def hopkins_signed(h):
    if h >= 0.5:
        return float(-np.clip((h - .5) / (H_CLUSTER_ANCHOR-.5), 0, 1))
    return float(np.clip((.5-h) / (.5-H_REGULAR_ANCHOR), 0, 1))


def _translation_pairs(q, aspect, r_max):
    """Pair distances up to r_max (sorted) and the running sum of their translation
    edge-correction weights, for the window [0, aspect] x [0, 1]."""
    pairs = cKDTree(q).query_pairs(float(r_max), output_type='ndarray')
    if not len(pairs):
        return None, None
    delta = np.abs(q[pairs[:, 0]]-q[pairs[:, 1]])
    lengths = np.hypot(delta[:, 0], delta[:, 1])
    overlap = np.maximum((1-delta[:,0]/aspect)*(1-delta[:,1]), 1e-8)
    weights = 1. / overlap
    order = np.argsort(lengths)
    lengths, weights = lengths[order], weights[order]
    return lengths, np.r_[0., np.cumsum(weights)]


def ripley_multiscale(points, aspect=1., factors=RADII_FACTORS):
    """Translation-edge-corrected K estimator for a rectangular window.
    + signed average (r-L)/r represents inhibition/regularity.
    """
    p = validate_points(points)
    q = shape_points(p, aspect)
    n = len(q)
    area = float(aspect)
    spacing = math.sqrt(area / n)
    radii = spacing * np.asarray(factors, dtype=float)
    kvals = np.zeros(len(radii), dtype=float)
    gvals = np.zeros(len(radii), dtype=float)
    lengths, cumulative = _translation_pairs(q, aspect, radii[-1])
    if lengths is not None:
        pos = np.searchsorted(lengths, radii, side='right')
        kvals = area * 2 * cumulative[pos] / (n*(n-1))
        # Annular pair correlation: finite difference K / annular area.
        edges = np.r_[0., radii]
        wbins = cumulative[np.searchsorted(lengths, edges, side='right')]
        gvals = area * 2 * np.diff(wbins) / (n*(n-1)*np.pi*np.diff(edges**2))
    lvals = np.sqrt(kvals / np.pi)
    dev = lvals-radii
    rel = (radii-lvals)/radii
    return dict(radii=radii, k=kvals, l=lvals, l_minus_r=dev, g=gvals,
                signed_index=float(np.mean(rel)), spacing=spacing)


# ---------------------------------------------------------------- L(r) curve
CSR_ENVELOPE_SEED = 7
CSR_ENVELOPE_SIMS = 39      # min/max of 39 simulations = pointwise 95% two-sided band


PAIR_BUDGET = 1_000_000


def _pair_budget_r(n, aspect, pair_budget=PAIR_BUDGET):
    """Largest r whose expected pair count (under randomness) stays within the budget."""
    return math.sqrt(2 * aspect * pair_budget / (math.pi * n * n)) if n > 1 else math.inf


def l_curve_radii(n, aspect=1., steps=120, pair_budget=PAIR_BUDGET):
    """r grid for the L(r) plot: up to 1/4 of the short side (Ripley's usual limit),
    shortened for very large n so the pair list stays small."""
    short = min(float(aspect), 1.)
    r_max = min(.25 * short, _pair_budget_r(n, aspect, pair_budget))
    return np.linspace(0., r_max, int(steps) + 1)


def ripley_l_curve(points, aspect=1., radii=None):
    """L(r) = sqrt(K(r)/pi) on a fine r grid, same estimator as the score's Ripley part.
    Complete spatial randomness gives L(r) = r (the 45-degree line)."""
    p = validate_points(points)
    q = shape_points(p, aspect)
    n = len(q)
    r = l_curve_radii(n, aspect) if radii is None else np.asarray(radii, float)
    k = np.zeros(len(r))
    lengths, cumulative = _translation_pairs(q, aspect, r[-1])
    if lengths is not None:
        k = float(aspect) * 2 * cumulative[np.searchsorted(lengths, r, side='right')] / (n*(n-1))
    return dict(r=r, k=k, l=np.sqrt(k / np.pi), spacing=math.sqrt(aspect / n), n=n, aspect=float(aspect))


def csr_l_envelope(n, aspect, radii, sims=CSR_ENVELOPE_SIMS, seed=CSR_ENVELOPE_SEED):
    """Pointwise min/max of L(r) over `sims` complete-random patterns with the same n and canvas.
    Fixed seed: the band only depends on n, the aspect ratio and the r grid."""
    r = np.asarray(radii, float)
    return _csr_l_envelope_cached(int(n), float(aspect), tuple(np.round(r, 12)), int(sims), int(seed))


@lru_cache(maxsize=32)
def _csr_l_envelope_cached(n, aspect, radii, sims, seed):
    r = np.array(radii)
    rng = np.random.default_rng(seed)
    curves = np.array([ripley_l_curve(rng.random((n, 2)), aspect, r)['l'] for _ in range(sims)])
    lo, hi = curves.min(axis=0), curves.max(axis=0)
    lo.setflags(write=False); hi.setflags(write=False)
    return lo, hi


def l_axis_limit(l_max, r_standard):
    """Shared x and y axis limit (and tick step) for the square L(r) plot.
    Random / regular patterns keep the usual r range; when L(r) climbs higher
    (clustering), both axes grow to the next round number above it."""
    m = r_standard if l_max <= 1.08 * r_standard else l_max
    options = []
    for step in (.005, .01, .02, .025, .05, .1, .2, .5):
        ticks = math.ceil(m / step - 1e-9)
        if 3 <= ticks <= 9:
            options.append((round(ticks * step, 10), step))
    # Tightest round limit; on a tie, the finer tick step.
    return min(options) if options else (round(math.ceil(m / .5) * .5, 10), .5)


def l_curve_for_plot(points, aspect=1., steps=120):
    """L(r) for the square plot: both axes run from 0 to `axis_max`, and r is computed
    up to the same value (at most half the short side), so the curve spans the square.
    Within the usual range (1/4 of the short side) the curve is never cut off."""
    p = validate_points(points)
    n = len(p)
    base = l_curve_radii(n, aspect, steps)
    first = ripley_l_curve(p, aspect, base)
    top, step = l_axis_limit(float(first['l'].max()), float(base[-1]))
    r_end = max(float(base[-1]), min(top, .5 * min(float(aspect), 1.), _pair_budget_r(n, aspect)))
    curve = first if r_end <= base[-1] + 1e-12 else ripley_l_curve(p, aspect, np.linspace(0., r_end, steps + 1))
    curve.update(axis_max=top, tick_step=step, r_standard=float(base[-1]))
    return curve


def _true_ranges(r, flags, min_len=2):
    """'0.012-0.085; 0.150-0.200' for runs of True at least min_len grid points long."""
    out, start = [], None
    for i, f in enumerate(list(flags) + [False]):
        if f and start is None:
            start = i
        elif not f and start is not None:
            if i - start >= min_len:
                out.append(f'{r[start]:.3f}-{r[i - 1]:.3f}')
            start = None
    return '; '.join(out) if out else 'none'


def l_curve_summary(curve, envelope=None):
    """Numbers read off the L(r) plot: largest excess / deficit of L(r) - r, and the r ranges
    where the curve leaves the random band (above = clustered, below = regular)."""
    r = np.asarray(curve['r'])
    L = np.asarray(curve['l'])
    d = L - r
    i, j = int(np.argmax(d)), int(np.argmin(d))
    out = dict(lr_r_max=float(r[-1]),
               lr_max_L_minus_r=float(d[i]), lr_r_at_max=float(r[i]),
               lr_min_L_minus_r=float(d[j]), lr_r_at_min=float(r[j]))
    if envelope is not None:
        lo, hi = envelope
        out['lr_clustered_r'] = _true_ranges(r, L > hi)
        out['lr_regular_r'] = _true_ranges(r, L < lo)
    return out


def score_from_components(h, ripley_index):
    hs = hopkins_signed(h)
    rs = float(np.tanh(ripley_index / RIPLEY_SOFT_SCALE))
    total = SCORE_HOPKINS_WEIGHT*hs + SCORE_RIPLEY_WEIGHT*rs
    return float(np.clip(total, -1., 1.)), hs, rs


def fast_score(points, aspect=1., probes=None):
    h = hopkins(points, aspect, probes)
    rip = ripley_multiscale(points, aspect)
    sc, _, _ = score_from_components(h, rip['signed_index'])
    return sc


def nearest_neighbor(points, aspect=1.):
    q = shape_points(validate_points(points), aspect)
    n = len(q)
    nn = cKDTree(q).query(q, k=2)[0][:, 1]
    expected = .5 * math.sqrt(aspect / n)
    # Donnelly (1978) edge correction: border points have no outside neighbours,
    # so the classic CSR expectation is too small and NNI reads ~3% too high at n=180.
    perimeter = 2 * (aspect + 1)
    expected_edge = expected + (.0514 + .041 / math.sqrt(n)) * perimeter / n
    return dict(nni=float(nn.mean()/expected), nni_edge_corrected=float(nn.mean()/expected_edge),
                nn_mean=float(nn.mean()),
                nn_std=float(nn.std()), nn_cv=float(nn.std()/nn.mean()) if nn.mean()>0 else 0.)


def quadrat_indices(points, grids=(4, 8, 12)):
    p = validate_points(points)
    results = {}
    for g in grids:
        hx = np.minimum((p[:,0]*g).astype(int), g-1)
        hy = np.minimum((p[:,1]*g).astype(int), g-1)
        counts = np.bincount(hy*g + hx, minlength=g*g).astype(float)
        results[f'quadrat_vmr_{g}x{g}'] = float(counts.var() / counts.mean())
        results[f'quadrat_occupied_{g}x{g}'] = int(np.count_nonzero(counts))
    return results


def voronoi_area_stats(points, aspect=1., resolution=None):
    """Approximate clipped Voronoi cell areas using a raster nearest-site partition.
    This is explicitly NOT exact polygonal Voronoi clipping.
    The grid grows with n (≥160, ~64 grid cells per point) so large point sets
    are not reduced to a handful of pixels per cell.
    """
    p = validate_points(points)
    if resolution is None:
        resolution = max(160, int(math.ceil(8 * math.sqrt(len(p)))))
    yy, xx = np.meshgrid((np.arange(resolution)+0.5)/resolution,
                          (np.arange(resolution)+0.5)/resolution, indexing='ij')
    grid = np.column_stack((xx.ravel(), yy.ravel()))
    counts = np.bincount(cKDTree(shape_points(p,aspect)).query(shape_points(grid,aspect))[1], minlength=len(p)).astype(float)
    areas = counts / (resolution*resolution)
    mean = areas.mean()
    return dict(voronoi_area_mean=float(mean), voronoi_area_std=float(areas.std()),
                voronoi_area_cv=float(areas.std()/mean),
                voronoi_area_min=float(areas.min()), voronoi_area_max=float(areas.max()),
                voronoi_zero_cells=int(np.count_nonzero(counts==0)),
                voronoi_resolution=int(resolution))


def fourier_stats(points, side=128):
    p = validate_points(points)
    hist, _, _ = np.histogram2d(p[:,1], p[:,0], bins=[side, side], range=[[0,1],[0,1]])
    power = np.abs(np.fft.fftshift(np.fft.fft2(hist - hist.mean())))**2 / len(p)
    c = side//2
    yy, xx = np.indices(power.shape)
    radius = np.hypot(xx-c, yy-c)
    power[c,c] = 0
    low = (radius>=1) & (radius<=5)
    mid = (radius>=6) & (radius<=30)
    non_dc = radius >= 1
    base = power[non_dc].mean()
    # Poisson CSR expectation S(k)≈1 for nonzero wavevectors (finite sampling noise).
    peak = float(np.quantile(power[mid], .995)/max(base, 1e-10))
    theta = np.mod(np.arctan2(yy-c, xx-c), np.pi)
    bins = np.clip((theta[mid] / np.pi * 12).astype(int), 0, 11)
    # Mean (not sum) per sector: the pixel grid puts 200–250 pixels in different
    # sectors, which alone made random patterns look anisotropic.
    angular = (np.bincount(bins, weights=power[mid], minlength=12)
               / np.maximum(np.bincount(bins, minlength=12), 1))
    anisotropy = float((angular.max()-angular.min()) / max(angular.mean(),1e-10))
    return dict(structure_factor_low_k=float(power[low].mean()),
                structure_factor_mid_k=float(power[mid].mean()),
                spectral_peak_ratio=peak, spectral_anisotropy=anisotropy)


def analyze(points, aspect=1., seed=HOPKINS_PROBE_SEED, probes=None):
    """`seed` only selects the Hopkins probe layout. Leave it at the default so
    every tab, the CLI and the optimizer report the same score for the same points."""
    p = validate_points(points)
    h = hopkins(p, aspect, probes if probes is not None else make_hopkins_probes(len(p), aspect, seed=seed))
    rip = ripley_multiscale(p, aspect)
    score, hs, rs = score_from_components(h, rip['signed_index'])
    nn = nearest_neighbor(p, aspect)
    vor = voronoi_area_stats(p,aspect)
    quad = quadrat_indices(p)
    four = fourier_stats(p)
    result = dict(n_points=len(p), aspect=float(aspect), score=score,
                  hopkins_h=h, hopkins_component=hs, ripley_component=rs,
                  ripley_index=rip['signed_index'], ripley_spacing=rip['spacing'],
                  x_mean=float(p[:,0].mean()), x_std=float(p[:,0].std()),
                  x_var=float(p[:,0].var()), y_mean=float(p[:,1].mean()),
                  y_std=float(p[:,1].std()), y_var=float(p[:,1].var()),
                  xy_cov=float(np.cov(p.T, ddof=0)[0,1]),
                  xy_corr=float(np.corrcoef(p.T)[0,1]) if np.std(p[:,0])*np.std(p[:,1])>1e-12 else 0.)
    for i, factor in enumerate(RADII_FACTORS):
        label = f'{factor:.2f}'.replace('.','p')
        result[f'ripley_r_{label}'] = float(rip['radii'][i])
        result[f'ripley_k_{label}'] = float(rip['k'][i])
        result[f'ripley_l_{label}'] = float(rip['l'][i])
        result[f'ripley_l_minus_r_{label}'] = float(rip['l_minus_r'][i])
        result[f'pair_g_{label}'] = float(rip['g'][i])
    result.update(nn)
    result.update(vor)
    result.update(quad)
    result.update(four)
    return result


# Pattern families. "ms_<small>_<large>": structure at the scale of a few dot spacings
# (small) versus the arrangement over the whole canvas (large).
PATTERN_LABELS = {
    'random': '完全隨機',
    'cluster': '群聚',
    'regular': '規律',
    'hybrid': '群聚＋隨機背景點',
    'ms_cluster_random': '小尺度群聚／大尺度隨機',
    'ms_random_cluster': '小尺度隨機／大尺度群聚',
    'ms_regular_cluster': '小尺度均勻／大尺度群聚',
    'ms_cluster_regular': '小尺度群聚／大尺度均勻',
    'ms_regular_random': '小尺度均勻／大尺度隨機',
    'ms_random_regular': '小尺度隨機／大尺度均勻',
}
PATTERN_LABELS_EN = {
    'random': 'Complete spatial randomness (CSR)',
    'cluster': 'Clustered',
    'regular': 'Regular',
    'hybrid': 'Clusters + random background',
    'ms_cluster_random': 'Small-scale clustered, large-scale random',
    'ms_random_cluster': 'Small-scale random, large-scale clustered',
    'ms_regular_cluster': 'Small-scale regular, large-scale clustered',
    'ms_cluster_regular': 'Small-scale clustered, large-scale regular',
    'ms_regular_random': 'Small-scale regular, large-scale random',
    'ms_random_regular': 'Small-scale random, large-scale regular',
}
HYBRID_KINDS = tuple(k for k in PATTERN_LABELS if k == 'hybrid' or k.startswith('ms_'))


def _to_unit(q, aspect):
    """Physical window [0,aspect]x[0,1] -> normalized [0,1]^2."""
    return np.clip(q / np.array([aspect, 1.]), 0, 1)


def _redraw_outside(q, centers, member, scale, rng, aspect, tries=200):
    """Offspring that land off-canvas are redrawn around their own parent (no edge pile-up)."""
    for _ in range(tries):
        out = (q[:,0] < 0) | (q[:,0] > aspect) | (q[:,1] < 0) | (q[:,1] > 1)
        if not out.any():
            break
        q[out] = centers[member[out]] + rng.normal(0, 1, (int(out.sum()), 2)) * scale
    return q


def _lattice(k, aspect, rng, jitter=0.):
    """About k cell centres on a near-square grid over the physical window."""
    nx = max(1, int(round(math.sqrt(k * aspect))))
    ny = max(1, int(math.ceil(k / nx)))
    ys, xs = np.mgrid[:ny, :nx]
    c = np.column_stack(((xs.ravel() + .5) / nx * aspect, (ys.ravel() + .5) / ny))
    if jitter:
        c += rng.normal(0, jitter, c.shape) * np.array([aspect / nx, 1. / ny])
    return c, nx, ny


def _patch_mask(aspect, frac, rng, cells=60000):
    """A few large organic patches covering `frac` of the canvas (thresholded sum of wide bumps)."""
    gy = max(60, int(round(math.sqrt(cells / aspect))))
    gx = max(60, int(round(gy * aspect)))
    X, Y = np.meshgrid((np.arange(gx) + .5) / gx * aspect, (np.arange(gy) + .5) / gy)
    short = min(aspect, 1.)
    k = max(2, int(round(rng.uniform(2, 4.5) * math.sqrt(max(aspect, 1 / aspect)))))
    field = np.zeros_like(X)
    for _ in range(k):
        cx, cy = rng.uniform(.12, .88) * aspect, rng.uniform(.12, .88)
        w = rng.uniform(.09, .16) * short
        field += rng.uniform(.6, 1.) * np.exp(-((X - cx)**2 + (Y - cy)**2) / (2 * w * w))
    return field > np.quantile(field, 1 - frac)


def _mask_sampler(mask, aspect, rng):
    iy, ix = np.nonzero(mask)
    gy, gx = mask.shape
    def sample(m):
        pick = rng.integers(len(iy), size=m)
        return np.column_stack(((ix[pick] + rng.random(m)) / gx * aspect, (iy[pick] + rng.random(m)) / gy))
    return sample


def _hard_core(n, d, sample, rng, rounds=400):
    """Random sequential addition: points from `sample`, none closer than d.
    d shrinks a little whenever the region is too full to take more points."""
    pts = np.empty((0, 2))
    for _ in range(rounds):
        need = n - len(pts)
        if need <= 0:
            break
        cand = sample(max(64, 6 * need))
        if len(pts):
            cand = cand[cKDTree(pts).query(cand)[0] >= d]
        if len(cand) > 1:
            keep = np.ones(len(cand), bool)
            pairs = cKDTree(cand).query_pairs(d, output_type='ndarray')
            if len(pairs):
                # Same result as adding the candidates one at a time in order.
                for i, j in pairs[np.argsort(pairs[:, 1], kind='stable')]:
                    if keep[i]:
                        keep[j] = False
            cand = cand[keep]
        added = cand[:need]
        pts = np.vstack((pts, added))
        if len(added) < max(1, .02 * need):
            d *= .97
    if len(pts) < n:   # practically unreachable; fill without the distance rule
        pts = np.vstack((pts, sample(n - len(pts))))
    return pts[:n]


def _multiscale(n, kind, s, rng, aspect):
    """The six ms_* families, built in physical units (height 1) so they stay isotropic.
    s = strength 0..1: how pronounced both structures are."""
    area = float(aspect)
    spacing = math.sqrt(area / n)
    if kind in ('ms_cluster_random', 'ms_cluster_regular'):
        # Small tight clumps (Thomas-type offspring). Parents: random or on a grid.
        if kind == 'ms_cluster_random':
            k = max(2, int(round(n / 5)))
            centers = rng.random((k, 2)) * np.array([aspect, 1.])
            member = rng.integers(0, k, n)
        else:
            centers, _, _ = _lattice(max(2, int(round(n / 5))), aspect, rng, jitter=.06)
            k = len(centers)
            member = rng.permutation(np.arange(n) % k)   # equal clump sizes
        sigma = math.sqrt(area / k) * (.20 - .14 * s)
        q = centers[member] + rng.normal(0, sigma, (n, 2))
        return _redraw_outside(q, centers, member, sigma, rng, aspect)
    if kind in ('ms_random_cluster', 'ms_regular_cluster'):
        # A few large patches hold all points; inside them points are random or evenly spaced.
        frac = .50 - .32 * s
        mask = _patch_mask(aspect, frac, rng)
        sample = _mask_sampler(mask, aspect, rng)
        if kind == 'ms_random_cluster':
            return sample(n)
        local = math.sqrt(frac * area / n)
        return _hard_core(n, local * (.45 + .30 * s), sample, rng)
    if kind == 'ms_regular_random':
        # Hard-core (no two dots closer than d) but no lattice: L(r) returns to r at large r.
        sample = lambda m: rng.random((m, 2)) * np.array([aspect, 1.])
        return _hard_core(n, spacing * (.40 + .32 * s), sample, rng)
    if kind == 'ms_random_regular':
        # Stratified: equal counts in each coarse cell, uniformly random inside the cell.
        per_cell = max(2, int(round(10 - 6 * s)))
        _, nx, ny = _lattice(max(1, int(round(n / per_cell))), aspect, rng)
        cell = rng.permutation(np.arange(n) % (nx * ny))
        cx, cy = cell % nx, cell // nx
        return np.column_stack(((cx + rng.random(n)) / nx * aspect, (cy + rng.random(n)) / ny))
    raise ValueError('未知分布模式: ' + kind)


def random_pattern(n=180, kind='random', strength=None, rng=None, aspect=1.):
    """Generated patterns: random, cluster, regular, the hybrid family (see HYBRID_KINDS),
    'hybrid_any' (one hybrid at random) and 'surprise' (any family).
    strength 0-1 is variation parameter, NOT promised output score.
    """
    if n < 3:
        raise ValueError('點數不可小於 3')
    rng = np.random.default_rng() if rng is None else rng
    kind_map = {'隨機':'random','群聚':'cluster','規律':'regular','混合':'hybrid_any','隨機混合':'surprise'}
    kind_map.update({label: key for key, label in PATTERN_LABELS.items()})
    kind = kind_map.get(kind,kind)
    if kind == 'surprise':
        kind = str(rng.choice(['random', 'cluster', 'regular', 'hybrid_any']))
    if kind == 'hybrid_any':
        kind = str(rng.choice(HYBRID_KINDS))
    if strength is None:
        strength = float(rng.uniform(.35,.9))
    strength = float(np.clip(strength,0,1))
    if kind == 'random':
        return rng.random((n,2)),kind
    if kind == 'cluster':
        groups = max(2, int(round(math.sqrt(n)/2.8)))
        centers = rng.uniform(.1,.9,(groups,2))
        member = rng.integers(0, groups, n)
        sigma = .17 - .15*strength
        # Isotropic on the physical canvas (height = 1): clusters stay round on wide images.
        scale = np.array([sigma/aspect, sigma])
        p = centers[member] + rng.normal(0,1,(n,2))*scale
        # Redraw points that land off-canvas. v1.0 clipped them, which stacked up to
        # ~7% of the points exactly on the frame edge as artificial lines.
        for _ in range(200):
            out = np.any((p < 0) | (p > 1), axis=1)
            if not out.any():
                break
            p[out] = centers[member[out]] + rng.normal(0,1,(int(out.sum()),2))*scale
        return np.clip(p,0,1),kind
    if kind == 'regular':
        nx = max(2, round(math.sqrt(n*aspect)))
        ny = max(2, math.ceil(n/nx))
        # Select the closest n in a centered grid; near-square tiling.
        ys,xs = np.mgrid[:ny,:nx]
        candidates = np.c_[((xs.ravel()+.5)/nx), ((ys.ravel()+.5)/ny)]
        if len(candidates)>n:
            remove = rng.choice(len(candidates),size=len(candidates)-n, replace=False)
            candidates = np.delete(candidates,remove,axis=0)
        # Jitter relative to each axis' own grid spacing; reflect at the frame instead of clipping.
        jitter = .50*(1.-strength) * np.array([1./nx, 1./ny])
        p = candidates + rng.normal(0,1,candidates.shape)*jitter
        p = 1 - np.abs(1 - np.abs(p))
        return np.clip(p,0,1),kind
    if kind == 'hybrid':
        ratio = .2+.65*strength
        cn = max(int(round(n*ratio)), min(n, 3))   # cluster part needs >= 3 points
        cl,_ = random_pattern(cn, 'cluster', strength, rng,aspect)
        return np.vstack((cl,rng.random((n-cn,2)))),kind
    if kind.startswith('ms_'):
        return _to_unit(_multiscale(n, kind, strength, rng, float(aspect)), aspect), kind
    raise ValueError('未知分布模式: '+kind)


def draw_points(points, size=(800,800), dot_radius=3, background=(255,255,255)):
    """RGB uint8 array with dark anti-aliased dots (what render_points saves)."""
    p = validate_points(points)
    w,h = (int(size[0]),int(size[1]))
    canvas = np.empty((h,w,3), np.uint8)
    canvas[:] = np.asarray(background, np.uint8)
    for x,y in p:
        cx = int(round(x*(w-1)))
        cy = int(round(y*(h-1)))
        cv2.circle(canvas,(cx,cy),int(dot_radius),(18,18,18),-1,cv2.LINE_AA)
    return canvas


def render_points(points, path, size=(800,800), dot_radius=3, background=(255,255,255)):
    canvas = draw_points(points, size, dot_radius, background)
    path = Path(path)
    path.parent.mkdir(parents=True,exist_ok=True)
    # Pillow handles Unicode filepaths on Windows reliably. Canvas is already RGB.
    Image.fromarray(canvas).save(path)
    return path


def extract_dots(path, threshold=140, min_area=5, invert=False):
    arr = load_image(path, 'L')
    mask = arr > threshold if invert else arr < threshold
    labels, count = ndimage.label(mask, structure=np.ones((3,3),bool))
    sizes = np.bincount(labels.ravel())
    ids = np.where(sizes >= min_area)[0]
    ids = ids[ids != 0]
    if len(ids) < 3:
        raise ValueError('只找到少於 3 個連通點，請調整閾值／最小面積。')
    yx = np.array(ndimage.center_of_mass(mask, labels, ids),dtype=float)
    h,w = arr.shape
    p = np.column_stack((yx[:,1]/max(1,w-1),yx[:,0]/max(1,h-1)))
    return validate_points(p),float(w/h),dict(width=w,height=h, components=count, detected=len(ids),
                                              warning='重疊或相連的黑點可能被合併成一點。')


def load_points_data(path, width=1., height=1., auto_bbox=False):
    """CSV columns x,y; TXT comma/space; JSON points with optional width/height.
    Uses explicit canvas dimensions when data aren't normalized; no silent crop.
    """
    path = Path(path)
    if path.suffix.lower()=='.json':
        obj = json.loads(path.read_text(encoding='utf-8-sig'))
        if isinstance(obj,dict):
            width = float(obj.get('width',width))
            height = float(obj.get('height',height))
            obj = obj['points']
        if isinstance(obj,list) and obj and isinstance(obj[0],dict):
            p = np.array([[float(z['x']),float(z['y'])] for z in obj])
        else:
            p = np.asarray(obj,float)
    else:
        import re
        lines = path.read_text(encoding='utf-8-sig').splitlines()
        filtered = [line.strip() for line in lines if line.strip() and not line.lstrip().startswith('#')]
        if not filtered:
            raise ValueError('沒有座標資料')
        def tokens_of(line):
            # Tolerate quoted CSV cells such as "x","y" or "0.12","0.40".
            return [t.strip('"\'') for t in re.split(r'[,;\t ]+',line.strip()) if t.strip('"\'')]
        first_tokens=[t.lower() for t in tokens_of(filtered[0])]
        try:
            if 'x' in first_tokens and 'y' in first_tokens:
                xidx,yidx=first_tokens.index('x'),first_tokens.index('y')
                p=np.array([[float(tokens[xidx]), float(tokens[yidx])]
                            for line in filtered[1:]
                            for tokens in [tokens_of(line)]],dtype=float)
            else:
                p=np.array([[float(z) for z in tokens_of(line)[:2]]
                            for line in filtered],dtype=float)
        except (ValueError, IndexError) as exc:
            raise ValueError('無法讀取座標：第一列需為 x,y 標題或數字，之後每列至少兩個數字。'
                             f'（{exc}）') from exc
    if p.ndim != 2 or p.shape[1] != 2:
        raise ValueError('座標資料須包含 x,y 兩欄')
    if auto_bbox:
        # Assumes x and y share one unit (e.g. both pixels); the window becomes the data's bounding box.
        mn = p.min(axis=0); span = p.max(axis=0)-mn
        if span.min() <= 1e-12 * max(1., span.max()):
            raise ValueError('點全部落在同一條水平或垂直線上，無法依自身邊界縮放。')
        p = (p-mn)/span
        aspect = float(span[0]/span[1])
    elif np.max(p)>1 or np.min(p)<0:
        p = p/np.array([width,height])
        aspect = float(width/height)
    else:
        aspect = float(width/height)
    return validate_points(p),aspect


def save_points_csv(path, points):
    path = Path(path)
    path.parent.mkdir(parents=True,exist_ok=True)
    with path.open('w',newline='',encoding='utf-8-sig') as f:
        writer = csv.writer(f)
        writer.writerow(('x','y'))
        writer.writerows([[f'{x:.9f}', f'{y:.9f}'] for x,y in validate_points(points)])


def save_metrics_csv(path, rows):
    path=Path(path)
    path.parent.mkdir(parents=True,exist_ok=True)
    if not rows: return
    keys = list(dict.fromkeys(k for r in rows for k in r))
    with path.open('w',newline='',encoding='utf-8-sig') as f:
        writer=csv.DictWriter(f,fieldnames=keys,extrasaction='ignore')
        writer.writeheader()
        writer.writerows(rows)


def image_skeleton(path, threshold=150, invert=False, max_size=1050):
    img = load_image(path, 'L')
    h,w = img.shape
    if max(h,w)>max_size:
        scale=max_size/max(h,w)
        img=cv2.resize(img,(round(w*scale),round(h*scale)),interpolation=cv2.INTER_AREA)
    mask = img > threshold if invert else img < threshold
    # Skeleton pixels concentrate the dot source on the strokes rather than a thick outline.
    from skimage.morphology import skeletonize
    labels,count = ndimage.label(mask)
    sizes = np.bincount(labels.ravel())
    mask = mask & (sizes[labels] >= 12)
    skel = skeletonize(mask)
    yx = np.column_stack(np.nonzero(skel))
    if len(yx)<3: raise ValueError('找不到足夠的線條，請確認線條顏色／閾值。')
    hh,ww = img.shape
    xy = np.column_stack((yx[:,1]/max(1,ww-1), yx[:,0]/max(1,hh-1)))
    return xy,float(ww/hh),dict(original_width=w,original_height=h,stroke_pixels=int(mask.sum()),
                                skeleton_pixels=len(xy), processed_width=ww,processed_height=hh)


def evenly_sample_strokes(stroke_xy, n, aspect=1., seed=15):
    """Weighted farthest-point stroke sampling, with slight randomized first seed.
    It distributes points across strokes; not a promise of uniform arclength on every path.
    """
    stroke = np.asarray(stroke_xy,float)
    if len(stroke)<3: raise ValueError('線條點不足')
    rng=np.random.default_rng(seed)
    if len(stroke)>40000:
        stroke=stroke[rng.choice(len(stroke),40000,replace=False)]
    physical = shape_points(stroke,aspect)
    n=int(n)
    # Iterative farthest-site + density correction.
    selected=[]
    start=int(rng.integers(len(stroke)))
    dmin=np.sum((physical-physical[start])**2,axis=1)
    selected.append(start)
    for _ in range(n-1):
        # Diversify ties in large line drawings deterministically.
        choice=int(np.argmax(dmin + rng.random(len(dmin))*1e-15))
        selected.append(choice)
        dmin=np.minimum(dmin,np.sum((physical-physical[choice])**2,axis=1))
    points=stroke[selected].copy()
    if len(stroke)<n: # duplicate use unavoidable when image lacks enough pixels
        points += rng.normal(0,1e-5,points.shape)
    return np.clip(points,0,1)


def displacement_stats(original, final, aspect):
    dist=np.linalg.norm(shape_points(final-original,aspect),axis=1)
    return dict(total_movement=float(dist.sum()), mean_movement=float(dist.mean()),
                max_movement=float(dist.max()), rms_movement=float(np.sqrt(np.mean(dist**2))),
                unchanged_001=int(np.sum(dist<.01)))


def optimize_pattern(original, target, aspect=1., stroke_xy=None, iterations=1600,
                     tolerance=.035, max_stroke_distance=0.09, min_stroke_retention=0.65,
                     seed=2026, progress:Callable|None=None,
                     cancellation:Callable|None=None, probes:HopkinsProbes|None=None):
    """Heuristic constrained search, NOT a proof of globally minimum displacement.
    First seeks a score near target, then minimizes identity-tracked displacement and
    stroke distance while maintaining score tolerance. Allows infeasibility warnings.
    `seed` drives the search only; the score always uses the shared Hopkins probes,
    so the optimized score equals what analyze() reports anywhere else.
    """
    p0=validate_points(original).copy()
    target=float(np.clip(target,-1,1)); n=len(p0)
    iterations=max(0,int(iterations))
    rng=np.random.default_rng(seed)
    probes=make_hopkins_probes(n,aspect) if probes is None else probes
    stroke=None
    if stroke_xy is not None and len(stroke_xy):
        stroke_xy=np.asarray(stroke_xy,float)
        stroke=cKDTree(shape_points(stroke_xy,aspect))
    else:
        stroke_xy=None
    mean_spacing=math.sqrt(aspect/n)
    unit=np.array([aspect,1.])   # physical -> normalized: divide by this

    def off_stroke(p):
        return stroke.query(shape_points(p,aspect))[0] if stroke is not None else None

    def retention_of(off_each):
        return float(np.mean(off_each < .025)) if off_each is not None else float('nan')

    def evaluate(p, off_each=None):
        score=fast_score(p,aspect,probes)
        dv=shape_points(p-p0,aspect)
        move=float(np.linalg.norm(dv,axis=1).mean()/mean_spacing)
        if stroke is not None:
            if off_each is None:
                off_each=off_stroke(p)
            off=float(np.mean(off_each)/mean_spacing)
        else:
            off=0.
        # Target accuracy takes priority. Prioritize staying on strokes & short movements.
        miss=abs(score-target)
        cost=20.*(max(0.,miss-tolerance)**2)/(.15**2) + .65*move + .45*off + 1.5*miss
        return score,cost,move,off

    def candidates(k):
        """Random positions that already satisfy the per-point off-stroke limit."""
        if stroke_xy is None or max_stroke_distance is None:
            return rng.random((k,2))
        base=stroke_xy[rng.integers(len(stroke_xy),size=k)]
        ang=rng.uniform(0,2*np.pi,k)
        rad=.95*max_stroke_distance*np.sqrt(rng.random(k))
        return np.clip(base+np.column_stack((np.cos(ang),np.sin(ang)))*rad[:,None]/unit,0,1)

    def crowded_index(p):
        q=shape_points(p,aspect)
        return int(np.argmin(cKDTree(q).query(q,k=2)[0][:,1]))

    current=p0.copy()
    curr_score,curr_cost,curr_move,curr_off=evaluate(current)
    initial_score=curr_score
    best_any=(curr_cost, current.copy(),curr_score)
    best_feasible=None
    # If score is already adequate, don't introduce needless movement.
    if abs(curr_score-target)<=tolerance or iterations==0:
        return dict(retained_within_025=retention_of(off_stroke(current)), points=current,
                    score=curr_score,initial_score=initial_score,target=target,tolerance=tolerance,
                    reached=abs(curr_score-target)<=tolerance,iterations=0,objective=curr_cost,
                    **displacement_stats(p0,current,aspect))

    report_step=max(1,iterations//40)
    best_miss=abs(curr_score-target)
    done=0
    for it in range(iterations):
        if cancellation is not None and cancellation():
            break
        done=it+1
        prop=current.copy()
        fraction=it/max(1,iterations-1)
        mode=int(rng.integers(0,10))
        j=int(rng.integers(n))
        typical=mean_spacing
        want_regular=target>curr_score
        # Primarily single-point proposals preserve the silhouette.
        if mode <= 3:
            scale=rng.choice([.18,.35,.7,1.4,2.8])*typical
            prop[j] += rng.normal(0,scale,2)/unit
        elif mode == 4 and stroke_xy is not None:
            # Relocate onto a random stroke pixel (low shape error, possibly long jump).
            prop[j]=stroke_xy[rng.integers(len(stroke_xy))]+rng.normal(0,.18*typical,2)/unit
        elif mode == 5:
            if want_regular:
                # Move a crowded (or random) dot to the emptiest allowed spot.
                if rng.random()<.5:
                    j=crowded_index(prop)
                choices=candidates(24)
                others=np.delete(prop,j,axis=0)
                gaps=cKDTree(shape_points(others,aspect)).query(shape_points(choices,aspect))[0]
                prop[j]=choices[np.argmax(gaps)]
            else:
                k=int(rng.integers(n))
                prop[j]=.75*prop[k]+.25*prop[j]+rng.normal(0,.10*typical,2)/unit
        elif mode == 6:
            # Local greedy step: best of 12 nearby spots (emptiest if regularizing, most
            # crowded if clustering). Replaces v1.0's two-dot swap, which left the
            # pattern geometrically unchanged and only exploited Hopkins index sampling.
            choices=np.clip(prop[j]+rng.normal(0,.6*typical,(12,2))/unit,0,1)
            others=np.delete(prop,j,axis=0)
            gaps=cKDTree(shape_points(others,aspect)).query(shape_points(choices,aspect))[0]
            prop[j]=choices[np.argmax(gaps) if want_regular else np.argmin(gaps)]
        elif mode == 7:
            # Break clumps using a repulsion move of a few closely spaced dots.
            q=shape_points(prop,aspect)
            tree=cKDTree(q)
            nn, ids=tree.query(q,k=2)
            j=int(np.argmin(nn[:,1]))
            d=q[j]-q[ids[j,1]]
            direction=d/max(1e-8,np.linalg.norm(d))
            if want_regular:
                prop[j]+=(direction*.7*typical+rng.normal(0,.12*typical,2))/unit
            else:
                prop[j]-=(direction*.3*typical)/unit
        elif mode == 8:
            # Multi-point short perturbation can escape single-dot score plateaus.
            ids=rng.choice(n,min(4,n),replace=False)
            scale=rng.choice([.2,.5,1.0])*typical
            prop[ids]+=rng.normal(0,scale,(len(ids),2))/unit
        else:
            # Shrink one moved point back toward its original stroke location.
            prop[j]=p0[j]+(prop[j]-p0[j])*rng.uniform(.0,.85)
        prop=np.clip(prop,0,1)
        off_each=off_stroke(prop)
        feasible=True
        if off_each is not None:
            if max_stroke_distance is not None and np.any(off_each > max_stroke_distance):
                feasible=False
            elif retention_of(off_each) + 1e-12 < min_stroke_retention:
                feasible=False
        if feasible:
            ps,pc,pm,po=evaluate(prop,off_each)
            new_miss=abs(ps-target)
            temperature=max(.005,.35*(1.-fraction)**1.6)
            if best_feasible is None and new_miss + .01 < best_miss:
                # Permit visible improvement regardless of small movement penalty.
                accept=True
            else:
                accept=(pc<curr_cost or rng.random()<math.exp(np.clip((curr_cost-pc)/temperature,-80,0)))
            if accept:
                current=prop;curr_score=ps;curr_cost=pc;curr_move=pm;curr_off=po
            if curr_cost<best_any[0]: best_any=(curr_cost,current.copy(),curr_score)
            if new_miss<best_miss: best_miss=new_miss
            if abs(curr_score-target)<=tolerance:
                if best_feasible is None or curr_cost<best_feasible[0]:
                    best_feasible=(curr_cost,current.copy(),curr_score)
        if progress is not None and (it%report_step==0 or it==iterations-1):
            candidate = best_feasible if best_feasible is not None else best_any
            progress(it+1,iterations, candidate[2], bool(best_feasible is not None))
    chosen=best_feasible if best_feasible is not None else best_any
    _, p, final_score = chosen
    return dict(retained_within_025=retention_of(off_stroke(p)), points=p,score=final_score,
                initial_score=initial_score,target=target,tolerance=tolerance,
                reached=abs(final_score-target)<=tolerance,
                iterations=done,objective=chosen[0],
                **displacement_stats(p0,p,aspect))
