# Point Pattern Studio v1.2 | Dot-pattern scoring and line-art pointillizing

English | [繁體中文](readme_tw.md)

A desktop tool (PyQt6) for Windows / macOS / Linux, plus a command-line interface. It

- generates random dot patterns (random, clustered, regular, and multi-scale hybrids),
- gives each pattern one score from **−1 (clustered)** through **0 (random)** to **+1 (regular)**, together with Ripley's L(r) plot and a full table of spatial statistics,
- turns a line drawing into dots and moves the dots until the pattern reaches a target score.

Everything runs locally; no data is uploaded anywhere. The GUI labels are in Traditional Chinese; plots and the CLI are in English.

## 1. Install and run

Python 3.10 or newer (tested on Windows 11 with Python 3.14).

**Windows**: double-click `run_windows.bat`. It finds Python through the `py` launcher, installs the packages only if something is missing (the first start needs internet; later starts work offline), and pauses with a message if any step fails.

> `run_windows.bat` must keep Windows CRLF line endings. With LF endings, `chcp 65001` plus the Chinese messages make cmd.exe split lines in the wrong places, and the script never reaches `app.py` (this was the v1.0 launch bug). If you edit the file, save it as CRLF, UTF-8 without BOM. The repository stores it byte-for-byte (`.gitattributes`), so clones and ZIP downloads keep CRLF.

Or from a terminal:

```bash
cd point_pattern_studio
python -m pip install -r requirements.txt
python app.py
```

**macOS / Linux**: `./run_macos_linux.sh`, or the same commands with `python3`. If Homebrew Python refuses `pip install` (externally-managed-environment), create a virtual environment first: `python3 -m venv ~/.venvs/pps && source ~/.venvs/pps/bin/activate`.

Packages: numpy, scipy, Pillow, opencv-python, scikit-image, matplotlib (L(r) plots), PyQt6 (PySide6 also works as a fallback).

v1.2 was tested on Windows 11 by driving all three tabs automatically in offscreen mode: batch generation in all 11 modes, import analysis, every built-in line drawing (place dots / optimize / export), and right-click copy. The macOS / Linux launcher has not been tested on a real machine.

## 2. The three tabs

### ① Batch generation (批次生成點圖)

- Set the number of images N, dots per image, random seed, pattern type, strength and canvas size.
- Types: `random` (complete spatial randomness, CSR), `cluster`, `regular` (jittered grid), the hybrid types below, and `surprise` (a random type for each image).
- "混合 (Hybrid)" picks one of the 7 hybrid types for each image; each hybrid type can also be chosen directly from the drop-down list.
- Output folder `output/batch_<date_time>/`: `pattern_XXXX.png`, `pattern_XXXX_xy.csv` (coordinates), `pattern_XXXX_Lr.png` (L(r) plot), `all_metrics.csv` (all statistics, including the L(r) results below), and `Lr_curves.csv` (every L(r) curve exactly as plotted: one row per pattern and r, with the random band).
- Click a row in the table to see the dots, the L(r) plot and all statistics.
- **Right-click any picture in any tab to copy it to the clipboard (paste into PowerPoint / Word) or save it.** The copy is the full-size image (batch dots: the canvas size you set; tab ③ dots: the exported PNG size), not the shrunken preview.

#### Hybrid (multi-scale) types

"Small scale" means the arrangement within a few dot spacings; "large scale" means the layout over the whole canvas. The CSV `pattern_type` code is `ms_<small>_<large>`.

| Type | How it is generated | L(r) signature | Score (strength 0.3 / 0.6 / 0.9, 180 dots) |
|---|---|---|---|
| Clusters + random background (`hybrid`, since v1.1) | some dots clustered, the rest random | above the dashed line throughout | −0.18 / −0.47 / −0.76 |
| Small-scale clustered, large-scale random (`ms_cluster_random`) | tight clumps of about 5 dots; clump positions completely random | jumps above the line at small r, returns towards it at large r | −0.92 / −0.98 / −1.00 |
| Small-scale random, large-scale clustered (`ms_random_cluster`) | 2–4 large patches, dots random inside, nothing outside | a straight line steeper than 45°, above the line throughout | −0.98 / −1.00 / −1.00 |
| Small-scale regular, large-scale clustered (`ms_regular_cluster`) | the same large patches, dots inside keep a minimum distance | L = 0 below the minimum distance, then climbs steeply above the line | −0.95 / −0.99 / −1.00 |
| Small-scale clustered, large-scale regular (`ms_cluster_regular`) | tight clumps on a regular grid, equal clump sizes | above at small r, then a plateau (no dots between clumps), rising again at the clump spacing | −0.49 / −0.73 / −0.93 |
| Small-scale regular, large-scale random (`ms_regular_random`) | hard-core process: random positions, no two dots too close, no grid | L = 0 below the minimum distance, back to the line at large r | +0.58 / +0.74 / +0.87 |
| Small-scale random, large-scale regular (`ms_random_regular`) | coarse grid with the same count (4–10 dots) in every cell, random inside each cell | hugs the line, slightly below it at large r | +0.14 / +0.16 / +0.15 |

**These types show that the score mostly measures small scales.** Hopkins uses nearest-neighbour distances, and the Ripley part only uses radii of 0.5–1.5 × the mean dot spacing (the pale yellow band in the L(r) plot). So:

- Tight clumps at small scale make a pattern score as clustered, however the clumps are laid out (rows 2 and 5).
- Large-scale clustering leaves large empty areas. Hopkins probes land in them, so the score is close to −1 even when the dots inside the patches are evenly spaced (rows 3 and 4).
- Large-scale regularity (row 7) is almost invisible: the eye and the score both say "random"; only `quadrat_vmr_4x4` is clearly below 1 (about 0.24–0.45, versus about 0.9 for random patterns).

#### Reading the L(r) plot

- **Dashed 45° line**: complete randomness, L(r) = r.
- **Blue curve above the line**: more neighbours within distance r than random, i.e. clustered. **Below**: fewer neighbours, i.e. regular.
- **Grey band**: minimum to maximum of L(r) over 39 completely random patterns with the same number of dots and canvas shape (a pointwise 95% band). Where the curve is inside the band, the pattern cannot be told apart from random at that scale.
- **Pale yellow band**: the radii used by the Ripley part of the score (0.5–1.5 × the mean dot spacing).
- **Square, same range and ticks on both axes**: r is measured with the canvas height = 1. For random and regular patterns both axes run from 0 to 1/4 of the short side (the usual Ripley range; 0–0.25 for an 800 × 800 canvas). L(r) of a clustered pattern goes beyond that, so both axes grow together to the next round number (for example 0–0.40), and r is computed up to the same value (at most 1/2 of the short side). Within the usual range the curve is always shown in full; at larger r a strongly clustered curve can leave through the top edge. For very many dots the range is shortened to keep the computation fast.
- The title gives the pattern type (or the file name for imports) and the score. The estimator is the same as in the score (translation edge correction).

#### L(r) results as numbers

The plot is also summarized in numbers (batch `all_metrics.csv`, the statistics tables and exports of tabs ② and ③, and the CLI):

| Column | Meaning |
|---|---|
| `lr_clustered_r` | r ranges where the curve is above the grey band, e.g. `0.007-0.120` = significantly clustered at these scales; `none` = nowhere |
| `lr_regular_r` | r ranges where the curve is below the grey band = significantly regular at these scales |
| `lr_max_L_minus_r`, `lr_r_at_max` | largest L(r) − r and where it occurs (strongest clustering scale) |
| `lr_min_L_minus_r`, `lr_r_at_min` | smallest L(r) − r and where it occurs (strongest regularity scale) |
| `lr_r_max` | largest r computed |

The grey band is pointwise. When many r values are checked at once, a completely random pattern will sometimes leave the band for a short stretch, so a range is only listed when at least 2 consecutive grid points are outside the band.

### ② Import an image or coordinates (匯入圖片／座標分析)

Supports black dots on white in PNG / JPG / TIFF / BMP; tick "反轉" (invert) for white dots on black. Dots are found by threshold plus connected-component centroids, so **touching or overlapping dots merge into one**. For exact work, import the coordinate CSV instead. For example, batch PNGs of the clustered and tight-clump types (800 px, dot radius 3) lose 20–35 dots on average to merging, so re-importing the PNG gives a different score than the batch table, while importing the matching `_xy.csv` gives exactly the same score.

After analysis, the L(r) plot appears next to the image. The status bar states the L(r) conclusion in one line (for example "L(r)：r = 0.019-0.104 顯著群聚", i.e. significantly clustered for r = 0.019–0.104), and the L(r) results above are listed at the top of the statistics table. Export also writes `analysed_Lr.png` and `analysed_Lr_curve.csv` (r, L, L − r, K and the random band).

Coordinate formats:

`CSV`:

```csv
x,y
0.12,0.25
0.43,0.82
0.89,0.11
```

`JSON`:

```json
{"width": 800, "height": 800, "points": [[100, 150], [245, 360], [580, 400]]}
```

A plain JSON coordinate matrix and TXT (one `x y` or `x,y` per line) also work. Coordinates already within 0–1 are used as they are; otherwise they are divided by the canvas width and height you enter. **Do not tick "資料依自身邊界縮放" (rescale to the data's own bounding box) unless you do not know the real canvas**: it changes Hopkins and the other statistics.

### ③ Line drawing → target score (線條圖 → 指定評分)

1. Upload a black-on-white line drawing (a transparent-background PNG also works; transparent areas count as white paper), or load a built-in drawing: fish, face, concentric circles, heart, heart with arrow, cat, dog, bear, rabbit, smiley, star, house, flower, tree, sun, snowflake, butterfly, moon and stars, umbrella (defined in `presets.py`; you can add your own).
2. Set the number of dots, e.g. 180, and press ①: the strokes are thinned to a skeleton and dots are placed along it at roughly even spacing.
3. Set the target score, e.g. `-0.13`, tolerance `0.035`, iterations `3600`.
4. Set "maximum off-stroke distance" and "minimum stroke retention" (e.g. 0.65). When these shape constraints make the target impossible, the program says "not reached" and suggests which setting to relax. **Measured: with the default maximum off-stroke distance of 0.09, the face only reaches about −0.42 and the fish about −0.96. To reach a near-random score such as −0.13, tick "允許離線移動不限距離" (allow unlimited off-stroke movement)**; `preview_face_optimization.png` was made that way.
5. Press ② to optimize; compare the original drawing, the starting dots, the adjusted dots and the L(r) plots of both; check Hopkins, Ripley, total and mean movement, shape retention, and the L(r) conclusion before and after (summary box and the `lr_*` rows of the table).
6. Press ③ to export: `before_points.png`, `optimized_points.png`, `optimized_overlay.png`, `before_Lr.png`, `optimized_Lr.png`, `Lr_curves.csv` (both L(r) curves), both coordinate CSVs, before/after statistics, and `optimization_report.json`.

> A near-random score does not mean the pattern is random at every scale. For example, the cat reaches −0.138 with unlimited movement, but its L(r) is still above the random band for r ≥ 0.03: the dots stay concentrated around the face outline, and the score mostly looks at small scales (see section 2).

**Important:** the optimizer is a **heuristic constrained search** (random proposals, annealing-style acceptance, and moves back towards the original position). It penalizes distance from the target, movement and off-stroke distance, and enforces the retention constraint, but it does not guarantee the mathematically minimal total movement. Some shapes (for example one long thin closed curve) cannot reach a score near 0 or +1 while keeping their outline; that is a geometric conflict in the request, not a bug.

## 3. How the score is computed

**The score only uses Hopkins + Ripley's L**; all other statistics are reported for reference and do not enter the score.

**Hopkins H** (2D, squared nearest-neighbour distances):

\[
H=\frac{\overline{u^2}}{\overline{u^2}+\overline{w^2}}
\]

\(u\): distance from a uniform probe to the nearest dot; \(w\): distance from each dot to its nearest other dot. Since v1.1, \(w\) uses **all** dots, and the probes are a fixed stratified jittered grid (seed 2026) of \(\max(2048,\ 24\lceil 0.1n\rceil)\) points. All tabs, the CLI and the optimizer share these probes, so **the same dots on the same canvas shape get the same score everywhere**, regardless of the order of the dots.

> v1.0 sampled 10% of the dots by index for \(w\). Shuffling the same dots (for example re-importing from PNG, which orders dots by scan position) changed the score (random patterns: standard deviation 0.036, maximum 0.11); the batch and import tabs used different seeds (difference SD 0.042); and the optimizer could "reach" a target by moving only the sampled dots. v1.1 keeps the expected value (random patterns still average about +0.01) and only removes the sampling noise; individual mid-range patterns moved by about ±0.03 (at most about 0.09), while extreme patterns and the line-drawing starting scores did not change.

(The original Hopkins test samples ~10% of the points so that \(H\) follows a Beta distribution under CSR and a p-value can be computed. This tool uses \(H\) only as a descriptive index without p-values, so using all points is the better choice.)

\[
S_H = \begin{cases}
-\operatorname{clip}((H-0.5)/(0.95-0.5),0,1), & H\geq0.5 \\
\operatorname{clip}((0.5-H)/(0.5-0.20),0,1), & H<0.5
\end{cases}
\]

**Ripley's L**: K estimated on the rectangular window with translation edge correction, averaged over five radii. Base length `d = sqrt(A/n)`; radii `0.50, 0.75, 1.0, 1.25, 1.50 × d`.

\[
D_L=\frac{1}{5}\sum_{i=1}^{5}\frac{r_i-L(r_i)}{r_i},\qquad S_L=\tanh(D_L/0.28)
\]

Combined:

\[
\boxed{PPDI=\mathrm{clip}(0.70 S_H+0.30 S_L,-1,1)}
\]

The Hopkins anchors 0.95 / 0.20, the Ripley scale 0.28 and the 70% / 30% weights are **fixed engineering choices**, not a unique statistical standard and not fitted to human ratings. A completely random pattern scores near 0 on average, but **any single random pattern need not score exactly 0**: the deviation includes sampling and estimation variance. ±1 are the bounded directions of the scale, not physical limits you can reliably reach.

### All statistics reported

| Group | CSV columns | Content |
|---|---|---|
| Main index | `score`, `hopkins_h`, `hopkins_component`, `ripley_index`, `ripley_component` | the composite score and its parts |
| Ripley per radius | `ripley_r_*`, `ripley_k_*`, `ripley_l_*`, `ripley_l_minus_r_*` | K, L, L − r at the 5 radii |
| L(r) results | `lr_*` | see "L(r) results as numbers" above |
| Pair correlation | `pair_g_*` | pair correlation in 5 annuli (binned, not a smoothed density estimate) |
| Clark–Evans | `nni`, `nni_edge_corrected`, `nn_mean`, `nn_std`, `nn_cv` | nearest-neighbour index and distance distribution; `nni_edge_corrected` uses the Donnelly edge correction (plain `nni` reads about 3% high at n = 180) |
| Voronoi | `voronoi_area_mean`, `voronoi_area_std`, `voronoi_area_cv`, `voronoi_area_min`, `voronoi_area_max`, `voronoi_zero_cells`, `voronoi_resolution` | clipped Voronoi cell areas **approximated on a nearest-site grid** (at least 160 × 160, finer for many dots: about 64 cells per dot), not exact polygons |
| Quadrat | `quadrat_vmr_4x4`, `quadrat_vmr_8x8`, `quadrat_vmr_12x12`, … | variance / mean of dot counts in 4×4, 8×8, 12×12 grids |
| Fourier | `structure_factor_low_k`, `structure_factor_mid_k`, `spectral_peak_ratio`, `spectral_anisotropy` | structure factor, spectral peak and direction features |
| XY coordinates | `x_mean`, `x_std`, `x_var`, `y_mean`, `y_std`, `y_var`, `xy_cov`, `xy_corr` | mean, SD, population variance, covariance and correlation of x and y on the 0–1 scale |

Distance-based statistics are corrected for the real width/height ratio (`aspect = width/height`); the x, y in CSV files are normalized coordinates.

## 4. Command line (no PyQt6 needed)

```bash
python cli.py generate --count 20 --points 180 --mode surprise --out output/experiment
python cli.py generate --count 12 --mode hybrid_any            # random choice of the 7 hybrid types
python cli.py generate --count 6 --mode ms_cluster_regular     # one specific multi-scale type
python cli.py analyze output/experiment/pattern_0001_xy.csv --width 1 --height 1
python cli.py analyze input_dots.png
python cli.py optimize samples/example_face.png --points 180 --target -0.13 --iterations 3500 --free
python cli.py presets                      # list the built-in drawings (Chinese name or English key)
python cli.py presets --out samples        # save all built-in drawings as PNG
python cli.py optimize cat --target -0.13 --free
python cli.py optimize heart_arrow --target -0.5 --free
```

`--free` removes the per-dot maximum off-stroke distance but **keeps** the minimum stroke retention (`--min-retention 0.65`); add `--min-retention 0` to release it completely (the drawing may become unrecognizable). `analyze` also has `--invert` (white dots on black) and `--auto-bbox`; `optimize` has `--invert` (white lines on black). `generate` and `analyze` also write the L(r) plots and curves (`*_Lr.png`, `Lr_curves.csv` / `Lr_curve.csv`) and add the `lr_*` results to the metrics CSV. `--mode` accepts `random`, `cluster`, `regular`, `hybrid`, `ms_cluster_random`, `ms_random_cluster`, `ms_regular_cluster`, `ms_cluster_regular`, `ms_regular_random`, `ms_random_regular`, `hybrid_any`, `surprise`.

Tests: `python -m pytest -q test_core.py`.

## 5. Limitations and advice

- The score is computed over **the whole canvas**, not only where there are lines. Dots placed only along a fish outline are statistically clustered, even if they are evenly spaced along the outline.
- Inhomogeneous intensity, very few dots, unclear borders or a wrong aspect ratio can make any single statistic misleading. Look at NNI, g(r), Fourier and the L(r) plot as well.
- The target score is one number; the same score can come from very different local structures.
- For scientific comparisons, fix the number of dots, the canvas aspect ratio, the program version and the random seed.
- Touching dots merge in PNG files, so a PNG is not a lossless record of the coordinates; keep the `_xy.csv` files for reproducible analysis.
- Many dots, many images or large line drawings take more time and memory. Each L(r) plot adds about 0.07 s per image in a batch.

## 6. What's new in v1.2 (2026-10-30)

- Right-click any picture to copy it to the clipboard or save it (all tabs; full-size image). Tab ③ dot previews now use the same size and dot style as the exported PNG.
- L(r) plots in ① batch and ② import: dashed 45° line for complete randomness, grey band from 39 random simulations, pale yellow band for the radii used by the score. The plot is square with the same range and ticks on both axes; plot text is English and the title has no image number.
- Tab ③ also shows L(r) plots, one for the starting dots and one for the optimized dots, saved with the export. Tab ③ shows its five pictures in one row and the summary box scrolls, so the window fits a 1280 × 720 laptop or projector.
- L(r) results as numbers (`lr_clustered_r`, `lr_regular_r`, …; see section 2) in the statistics table and CSV files, plus a one-line conclusion in the import status bar and the tab ③ summary. L(r) curves are saved as CSV (long format: pattern, r, L, L − r, K, random band).
- 6 new multi-scale hybrid types (table in section 2) and a "random hybrid type" mode. The existing `hybrid` type is unchanged. `surprise` now picks one of the 7 hybrid types 1/4 of the time, so **a surprise batch with the same seed differs from v1.1**.
- The score itself is unchanged: v1.1 and v1.2 give bit-identical statistics for the same dots.
- Fix: `hybrid` crashed with very few dots (3–4).
- New dependency: matplotlib (L(r) plots).

## 7. v1.1 fixes (2026-10-29)

**Launch**
- Double-clicking `run_windows.bat` did nothing useful: the file had LF line endings and cmd.exe misparsed it. Now CRLF; uses the `py` launcher, installs packages only when missing, and pauses with the reason when a step fails.

**Calculation**
- The Hopkins score depended on the order of the dots, the tabs used different seeds, and the optimizer could fake reaching a target: fixed by using all dots for \(w\) and one shared probe set (section 3).
- Cluster / hybrid modes clipped off-canvas dots onto the border (about 6.8% of the dots on the edge at strength 0.3): they are now redrawn. Cluster shapes and grid jitter are corrected for the canvas aspect ratio, so clusters on wide canvases are no longer stretched into ellipses.
- Fourier anisotropy summed the power in each direction sector, but sectors have different pixel counts (200–250), so even random patterns looked directional: now the sector mean (random-pattern anisotropy 0.40 → 0.31).
- Added `nni_edge_corrected`; the Voronoi grid now gets finer with more dots.
- "Rescale to bounding box" forced aspect ratio 1; it now uses the real aspect ratio of the data's bounding box. Quoted CSV fields are accepted.

**Optimizer**
- Removed the "swap two dots" move (it left the geometry unchanged and only exploited the index-based Hopkins sampling); replaced with a local best-of-12 move. "Jump to an empty spot" candidates are drawn within the allowed off-stroke band, so fewer proposals are wasted. Under the same settings the face now reaches −0.42 instead of −0.54.
- Fixed: `iterations=0` crashed; retention was hard-coded to 100% when the target was already met; progress did not update when proposals were rejected; cancelling counted one extra iteration.

**Images and interface**
- Transparent-background PNGs were read as all black (everything a line): transparent areas now count as white paper; phone photos are rotated by their EXIF tag.
- Previews and exported PNGs of non-square images were forced to 680 × 680 / 800 × 800 and distorted: the aspect ratio is now kept.
- "① Analyse strokes" runs in the background, so the window no longer freezes with many dots; errors show a short reason first, with the full traceback under "Show Details".
- 16 new built-in line drawings (`presets.py`), also usable by name from the CLI.

**Open suggestions**
- \(L=\sqrt{K/\pi}\) is concave, so there is a small Jensen bias that makes random patterns score slightly positive on average (about +0.01). The effect is small.
- Fourier and quadrat statistics are computed in normalized [0,1]² coordinates; on non-square canvases, directions and cell shapes are measured in the stretched space.
- The score uses the whole canvas as the window, so drawings made only of lines always lean clustered. Comparing "evenness along the strokes" would need a separate, stroke-based statistic.

## 8. References

- [R Journal (2022): Will the Real Hopkins Statistic Please Stand Up?](https://journal.r-project.org/articles/RJ-2022-055/)
- [spatstat: Ripley's L](https://search.r-project.org/CRAN/refmans/spatstat.explore/html/Lest.html)
- [spatstat: pair correlation](https://search.r-project.org/CRAN/refmans/spatstat.explore/html/pcf.html)

These references define the methods; **they do not propose or validate this project's composite PPDI score**.

## 9. License

GNU Affero General Public License v3.0 (see `LICENSE`).
