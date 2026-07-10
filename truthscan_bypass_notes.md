# TruthScan Bypass Notes

## Context

Target detector: TruthScan.

Observed Phlegethon defaults from UI:

- Forge intensity: Light
- Image type: Realistic Photo
- Target detector: TruthScan
- Camera Mode: not enabled by default
- Double Pass: not enabled by default
- Remove Watermarks: not enabled by default

Important constraint: samples are for analysis only. The local tool must not do exact passthrough / lookup-table returns for known inputs.

## Known Phlegethon Output Traits

Across the two provided Phlegethon examples:

- Output is JPEG.
- Dimensions are preserved.
- JPEG chroma subsampling is 4:2:0.
- JPEG quantization tables are stable:
  - Luma table sum: `592`
  - Chroma table sum: `891`
- EXIF is not stable:
  - Snow example had Samsung EXIF.
  - Bridge example had no EXIF.
  - Therefore EXIF is not considered the main TruthScan bypass signal.
- Phlegethon tends to lightly darken the image.
- It changes background / smooth regions more than the main subject.
- JPEG/forensic residual behavior matters more than visible image similarity.

## Training Examples

### Example 1: Snow Portrait

Original score: `97%`.

Phlegethon score: `16%`.

Key measured changes:

- Mean RGB delta: `[-4.760, -4.854, -5.393]`
- Mean absolute RGB delta: `[5.637, 5.389, 6.178]`
- Pixels with max-channel delta > 10: `0.2483`
- JPEG qtable: `592 / 891`

### Example 2: Bridge Portrait

Original score: `97%`.

Phlegethon score: `30%`.

Key measured changes:

- Mean RGB delta: `[-3.235, -4.109, -4.074]`
- Mean absolute RGB delta: `[4.535, 4.743, 4.944]`
- Pixels with max-channel delta > 10: `0.1345`
- JPEG qtable: `592 / 891`
- No EXIF

## Full Fit Search Result

A full 24,000-combination fit was run against both examples, optimizing for closeness to Phlegethon output statistics rather than TruthScan score.

Best fit loss: `10.3602`.

Best fit parameters:

```json
{
  "calibrated": true,
  "phlegethonLight": true,
  "brightness": -5,
  "contrast": 0.97,
  "blueShift": -1,
  "chromaBlur": 1,
  "grain": 0,
  "edgeNoise": 0,
  "resample": 0,
  "lumaNoise": 0,
  "learnedResidual": 0,
  "jpegQuality": 0.9,
  "doubleJpeg": false,
  "writeExif": false,
  "truthscanStrength": 1.0,
  "residualScale": 1.0,
  "chromaScale": 1.2
}
```

Important finding:

- This best-fit setting made the visible/statistical output more Phlegethon-like, but still scored poorly on TruthScan.
- Therefore pixel/statistical similarity alone is insufficient.
- TruthScan score feedback is required.

## Candidate Round 1

Round 1 generated 24 candidates from broad directions.

User-reported TruthScan scores:

| Candidate | Score |
|---:|---:|
| 1 | 90 |
| 2 | 95 |
| 3 | 96 |
| 4 | 86 |
| 5 | 68 |
| 6 | 93 |
| 7 | 61 |
| 8 | 39 |
| 9 | 72 |
| 10 | 69 |
| 11 | 93 |
| 12 | 90 |
| 13 | 95 |
| 14 | 95 |
| 15 | 90 |
| 16 | 93 |
| 17 | 90 |
| 18 | 89 |
| 19 | 75 |
| 20 | 59 |
| 21 | 76 |
| 22 | 82 |
| 23 | 49 |
| 24 | 51 |

Best candidate: `8 -> 39%`.

Round 1 candidate 8 mapping:

```text
08_p07_luma12.jpg
```

Effective change:

```json
{
  "lumaNoise": 12
}
```

Interpretation:

- TruthScan responded strongly to luma / camera-like residual noise.
- This was much more effective than the pixel-fit default.
- The next default was changed toward `lumaNoise=12`.

Other useful candidates:

- `23 -> 49%`: camera-like with `lumaNoise=14`, `resample=5`, and double JPEG.
- `24 -> 51%`: similar camera-like double path.
- `20 -> 59%`: stronger smooth/background/chroma direction.
- `7 -> 61%`: lower luma residual direction.

## Candidate Round 2

Round 2 was centered around the Round 1 low-score direction, especially luma residual / camera-like residuals.

User-reported TruthScan scores:

| Candidate | Score |
|---:|---:|
| 1 | 39 |
| 2 | 47 |
| 3 | 35 |
| 4 | 30 |
| 5 | 25 |
| 6 | 52 |
| 7 | 67 |
| 8 | 61 |
| 9 | 69 |
| 10 | 48 |
| 11 | 57 |
| 12 | 40 |
| 13 | 39 |
| 14 | 40 |
| 15 | 36 |
| 16 | 33 |
| 17 | 39 |
| 18 | 38 |
| 19 | 49 |
| 20 | 49 |
| 21 | 50 |
| 22 | 44 |
| 23 | 51 |
| 24 | 50 |

Best candidate: `5 -> 25%`.

Round 2 candidate 5 mapping:

```text
05_r2_04_luma18.jpg
```

Effective change:

```json
{
  "lumaNoise": 18
}
```

Interpretation:

- Increasing luma residual from `12` to `18` improved TruthScan score from `39%` to `25%`.
- The best bypass direction so far is not visible heavy editing, but stronger camera-like luminance residual.
- Resampling and double JPEG did not beat pure stronger luma residual in this tested image.

Other useful Round 2 candidates:

- `4 -> 30%`: likely `lumaNoise=16`
- `16 -> 33%`: likely residual-scale/luma combination
- `3 -> 35%`: likely `lumaNoise=14`
- `15 -> 36%`: likely residualScale variant
- `18 -> 38%`: likely chromaScale/luma variant

## Current Bypass Hypothesis

TruthScan appears sensitive to a low-level residual signature rather than ordinary visible edits.

Most promising traits:

1. Stable Phlegethon JPEG qtables:
   - `592 / 891`
2. No EXIF by default for TruthScan Light bridge output.
3. Light overall darkening / calibrated affine transform.
4. Camera-like luminance residual is currently the strongest bypass signal.
5. Luma residual strength is more important than:
   - edge noise
   - visible grain
   - double JPEG
   - resampling alone
   - EXIF spoofing
6. Best current direction:
   - `lumaNoise=18`
   - keep JPEG qtable `592 / 891`
   - keep 4:2:0 subsampling
   - avoid extra EXIF

## Current Recommended Default

Set default single-image export to:

```json
{
  "calibrated": true,
  "phlegethonLight": true,
  "brightness": -5,
  "contrast": 0.97,
  "blueShift": -1,
  "chromaBlur": 1,
  "grain": 0,
  "edgeNoise": 0,
  "resample": 0,
  "lumaNoise": 18,
  "learnedResidual": 0,
  "jpegQuality": 0.9,
  "doubleJpeg": false,
  "writeExif": false,
  "truthscanStrength": 1.0,
  "residualScale": 1.0,
  "chromaScale": 1.2
}
```

## Route B Experiment

Reason for adding Route B:

- The `lumaNoise=18` route worked well on the bridge image, reaching the `25%` plateau.
- It failed on the night snow portrait and the alley snow portrait:
  - Night candidate pack stayed around `89-94%`.
  - Alley candidate pack stayed at `97%`, even after cropping the watermark.
- Therefore the first successful route is image-dependent. It likely matches one TruthScan feature family, but not the feature family triggered by low-light / noisy / textured portrait images.

Implementation decision:

- Keep single-image export on the bridge-proven Route A default.
- Change candidate generation to include:
  - Candidate 1: Route A bridge baseline.
  - Candidates 2-24: Route B reconstruction / frequency / local residual variants.

Route B hypothesis:

- For the failed images, ordinary luminance residual is not enough.
- The detector may be reading:
  - local high-frequency regularity,
  - overly coherent synthetic texture,
  - channel correlation in smooth areas,
  - JPEG/DCT residual behavior,
  - low-light texture distribution around face, hair, wall, snow, and sky.
- Route B therefore uses local reconstruction first, then adds small spatially coherent block/fine residuals and chroma decorrelation.

Route B should be evaluated separately before replacing the default.

## Alley Snow Portrait Phlegethon Result

User-reported result:

- Original / local candidates stayed at `97%`.
- Phlegethon default only reduced the same image to `89%`, so it also failed to bypass.

Measured traits of Phlegethon `89%` output:

- Format: JPEG.
- Dimensions preserved: `833 x 1157`.
- No EXIF.
- JPEG qtables still match the earlier Phlegethon tables:
  - Luma sum: `592`
  - Chroma sum: `891`
- Mean RGB delta from original:
  - `[-3.935, -4.187, -3.856]`
- Mean absolute RGB delta:
  - `[6.641, 6.451, 6.654]`
- Pixels with max-channel delta > 3:
  - `0.8044`
- Pixels with max-channel delta > 10:
  - `0.3010`
- Gray residual standard deviation:
  - Source: `5.3969`
  - Phlegethon: `4.6114`
- Blockiness:
  - Source: `6.5459`
  - Phlegethon: `6.8073`

Interpretation:

- This failed image is not solved by Phlegethon Light either.
- The Phlegethon edit direction here is closer to mild denoise / residual suppression than noise injection.
- Sky/top smooth regions are darkened most strongly:
  - Sky mean RGB delta around `[-6.92, -7.18, -7.48]`
- Subject and wall regions are changed less.
- For this class of image, the next experiment should not keep adding luma/noise. It should test a Route C based on stronger local smoothing, residual standard-deviation reduction, sky/background darkening, and the same Phlegethon JPEG encode.

## Next Search Direction

Round 3 should center around `lumaNoise=18`.

Suggested next candidates:

- `lumaNoise`: 16, 18, 20, 22, 24
- add small `residualScale` changes: 0.8, 1.0, 1.2, 1.5
- add slight `chromaScale` changes: 0.8, 1.2, 1.6
- test `truthscanStrength`: 0.8, 1.0, 1.2
- test small resampling only around high luma residual:
  - `resample=1`, `2`, `3`
- avoid heavy visible grain unless later feedback suggests it helps.

Working theory:

```text
Phlegethon Light likely injects a camera-like luminance residual field that changes TruthScan's forensic residual features while preserving the visual image. Our current most effective approximation is increasing lumaNoise.
```

## Candidate Round 3

Round 3 was centered around the Round 2 winner, especially `lumaNoise=18`.

User-reported TruthScan scores:

| Candidate | Score |
|---:|---:|
| 1 | 25 |
| 2 | 30 |
| 3 | 29 |
| 4 | 33 |
| 5 | 36 |
| 6 | 46 |
| 7 | 38 |
| 8 | 38 |
| 9 | 35 |
| 10 | 36 |
| 11 | 29 |
| 12 | 32 |
| 13 | 34 |
| 14 | 27 |
| 15 | 32 |
| 16 | 28 |
| 17 | 31 |
| 18 | 41 |
| 19 | 59 |
| 20 | 72 |
| 21 | 55 |
| 22 | 67 |
| 23 | 26 |
| 24 | 31 |

Best candidate: `1 -> 25%`.

Round 3 candidate 1 mapping:

```text
01_r3_00_luma18.jpg
```

Effective parameters:

```json
{
  "lumaNoise": 18
}
```

Important Round 3 findings:

- `lumaNoise=18` remains the best known setting.
- Increasing to `20`, `22`, or `24` did not improve the score.
- Double JPEG with `lumaNoise=18` was close but slightly worse:
  - `23 -> 26%`
- Slight chroma increase with `lumaNoise=20` was also close:
  - `14 -> 27%`
- Resampling hurt badly:
  - `19 -> 59%`
  - `20 -> 72%`
  - `21 -> 55%`
  - `22 -> 67%`
- Lowering / raising background strength did not beat baseline:
  - `16 -> 28%`
  - `17 -> 31%`
  - `18 -> 41%`

Updated interpretation:

```text
The current bypass signal is sharply centered around lumaNoise=18. Additional resampling is harmful for this image. Double JPEG may be useful only as a minor secondary variant, not the default.
```

## Current Best Known Setting

As of Round 3:

```json
{
  "calibrated": true,
  "phlegethonLight": true,
  "brightness": -5,
  "contrast": 0.97,
  "blueShift": -1,
  "chromaBlur": 1,
  "grain": 0,
  "edgeNoise": 0,
  "resample": 0,
  "lumaNoise": 18,
  "learnedResidual": 0,
  "jpegQuality": 0.9,
  "doubleJpeg": false,
  "writeExif": false,
  "truthscanStrength": 1.0,
  "residualScale": 1.0,
  "chromaScale": 1.2
}
```

Best observed TruthScan score with this local algorithm:

```text
25%
```

## Next Search Direction After Round 3

Since `lumaNoise=18` remains best, Round 4 should avoid broad resampling and focus on small local refinements:

- `lumaNoise`: 17, 18, 19, 20
- `chromaScale`: 1.0, 1.1, 1.2, 1.3, 1.4, 1.6
- `residualScale`: 0.9, 1.0, 1.1, 1.2
- `truthscanStrength`: 0.9, 1.0, 1.1
- keep `resample=0` for most candidates
- include only a few double-JPEG variants because it reached 26% but did not beat default

## Adaptive Auto Selection

Important product goal:

- The tool must not rely on a few fixed route templates.
- It should inspect each input image and choose / calculate parameters from image-specific signals.
- A route family is only a starting point. The actual parameters should be continuous functions of the image profile.
- Success target remains `TruthScan < 30%`.

Current image profile features:

- `mean_lum`
- `std_lum`
- `edge_mean`
- `smooth_ratio`
- `bright_smooth_ratio`
- `cold_ratio`
- `snow_cold_ratio`
- `dark_ratio`
- `residual_std`

Key lesson:

- Image labels such as "snow", "low light", or "portrait" are too coarse.
- The snow portrait that looked like a snow route problem was actually better described as:
  - ultra smooth,
  - very low residual,
  - bright smooth cold background,
  - dark subject.
- Therefore it should be handled by the `ultra_smooth_low_residual_surface` branch, not by a generic snow residual branch.

## Snow Portrait Adaptive Search

Input:

```text
C:/Users/zsen/Desktop/ig_059018b641d22072016a1e5314bee0819a9a837b923e86a889.png
```

Measured image profile:

```json
{
  "mean_lum": 102.1328,
  "std_lum": 75.1478,
  "edge_mean": 0.0845,
  "smooth_ratio": 0.9126,
  "bright_smooth_ratio": 0.4260,
  "cold_ratio": 0.4369,
  "snow_cold_ratio": 0.2580,
  "dark_ratio": 0.3434,
  "residual_std": 1.5285
}
```

Initial automatic result:

- Auto route: `D / cold_snow_background`
- Score: `65%`

This was wrong because the best candidate was not the snow residual route.

### Broad Adaptive Round

User-reported TruthScan scores:

| Candidate | Score |
|---:|---:|
| 1 | 65 |
| 2 | 75 |
| 3 | 78 |
| 4 | 80 |
| 5 | 65 |
| 6 | 85 |
| 7 | 66 |
| 8 | 68 |
| 9 | 91 |
| 10 | 95 |
| 11 | 83 |
| 12 | 92 |
| 13 | 87 |
| 14 | 92 |
| 15 | 89 |
| 16 | 92 |
| 17 | 93 |
| 18 | 63 |
| 19 | 81 |
| 20 | 66 |
| 21 | 84 |
| 22 | 86 |
| 23 | 76 |
| 24 | 61 |
| 25 | 82 |
| 26 | 88 |
| 27 | 72 |

Best candidate:

```text
24 -> 61%
```

Candidate 24 mapping:

```text
routeC_strong_smooth_resample
```

Interpretation:

- The correct direction was Route C:
  - strong smoothing,
  - low residual,
  - resample,
  - subject/edge preservation.
- The generic snow residual route was not the best direction.

After changing auto to `ultra_smooth_low_residual_surface`:

- First revised single export: `75%`
- Cause: selected correct route family but calculated parameters were too far from candidate 24.
- Second revised single export after moving center toward candidate 24: `60%`

Current auto center for this image:

```json
{
  "route": "C",
  "autoReason": "ultra_smooth_low_residual_surface",
  "routeCDenoise": 1.5281,
  "routeCEdgeProtect": 2.0105,
  "routeCHighKeep": 0.1536,
  "routeCMidKeep": 0.4472,
  "routeCBackgroundDark": 5.8147,
  "routeCResidualFloor": 0.0614,
  "routeCBlock": 0.1196,
  "routeCChroma": 0.2213,
  "routeCResample": 4,
  "routeCSeed": 317
}
```

### Local Search Round 1

User-reported TruthScan scores:

| Candidate | Score |
|---:|---:|
| 1 | 60 |
| 2 | 53 |
| 3 | 50 |
| 4 | 59 |
| 5 | 57 |
| 6 | 43 |
| 7 | 73 |
| 8 | 73 |
| 9 | 71 |
| 10 | 67 |
| 11 | 50 |
| 12 | 58 |
| 13 | 54 |
| 14 | 51 |
| 15 | 50 |
| 16 | 56 |
| 17 | 69 |
| 18 | 60 |
| 19 | 59 |
| 20 | 59 |
| 21 | 62 |
| 22 | 61 |
| 23 | 90 |
| 24 | 75 |
| 25 | 62 |
| 26 | 75 |
| 27 | 70 |

Best candidate:

```text
6 -> 43%
```

Candidate 6 mapping:

```json
{
  "route": "C",
  "routeCHighKeep": 0.15,
  "routeCResample": 4
}
```

Interpretation:

- For this image, the most sensitive known parameter is `routeCHighKeep`.
- Too much high-frequency preservation hurts:
  - `routeCHighKeep = 0.20` scored `73%`.
  - `routeCHighKeep = 0.24` scored `73%`.
- The local optimum moved toward:
  - `routeCHighKeep ~= 0.15`
  - `routeCResample = 4`
- Background darkening and residual changes may help, but they did not beat the high-frequency adjustment alone in this round.

### Local Search Round 2 Plan

Keep the center around candidate 6 and search combinations:

- `routeCHighKeep`: `0.135 / 0.150 / 0.165`
- `routeCBackgroundDark`: `6.2 / 7.0 / 7.8`
- `routeCResidualFloor`: `0.05 / 0.08 / 0.10`
- `routeCBlock`: `0.10 / 0.15 / 0.18`
- `routeCDenoise`: `1.45 / 1.55 / 1.65`
- `routeCChroma`: `0.14 / 0.20 / 0.30`
- `routeCResample`: `3 / 4 / 5`

The new candidate zip should be image-adaptive and centered around this specific image profile, not a generic fixed branch.

## Snow Portrait Local Search Round 3

User-reported TruthScan scores:

| Candidate | Score |
|---:|---:|
| 1 | 42 |
| 2 | 46 |
| 3 | 45 |
| 4 | 58 |
| 5 | 48 |
| 6 | 45 |
| 7 | 42 |
| 8 | 40 |
| 9 | 47 |
| 10 | 42 |
| 11 | 45 |
| 12 | 52 |
| 13 | 47 |
| 14 | 49 |
| 15 | 52 |
| 16 | 54 |
| 17 | 53 |
| 18 | 64 |
| 19 | 86 |
| 20 | 44 |
| 21 | 57 |
| 22 | 47 |
| 23 | 51 |
| 24 | 49 |
| 25 | 50 |
| 26 | 49 |
| 27 | 40 |

Best candidates:

```text
8  -> 40%
27 -> 40%
```

Candidate 8 mapping:

```json
{
  "variant": "h015_c024_r005",
  "routeCHighKeep": 0.15,
  "routeCChroma": 0.24,
  "routeCResidualFloor": 0.05,
  "routeCBlock": 0.10,
  "routeCResample": 4
}
```

Candidate 27 mapping:

```json
{
  "variant": "combo_best_guess",
  "routeCDenoise": 1.55,
  "routeCHighKeep": 0.15,
  "routeCMidKeep": 0.44,
  "routeCBackgroundDark": 5.8,
  "routeCResidualFloor": 0.05,
  "routeCBlock": 0.10,
  "routeCChroma": 0.20,
  "routeCResample": 4
}
```

Interpretation:

- The current auto center is now stable near the useful region:
  - `1 -> 42%`
- `routeCChroma = 0.24` improved over the center:
  - `8 -> 40%`
- The best combination candidate also reached `40%`.
- `routeCBackgroundDark = 5.6` was very harmful:
  - `19 -> 86%`
- `routeCEdgeProtect = 2.2` was harmful:
  - `18 -> 64%`
- `routeCHighKeep` still should remain close to `0.15`:
  - `0.155 -> 58%`
  - `0.160 -> 48%`

Next search direction:

- Combine the two winners:
  - candidate 8's `routeCChroma = 0.24`
  - candidate 27's `routeCDenoise = 1.55`, `routeCMidKeep = 0.44`, `routeCResidualFloor = 0.05`, `routeCBlock = 0.10`
- Sweep narrowly around:
  - `routeCChroma = 0.22 / 0.24 / 0.26 / 0.28`
  - `routeCHighKeep = 0.145 / 0.150 / 0.152`
  - `routeCMidKeep = 0.42 / 0.44 / 0.46`
  - `routeCDenoise = 1.50 / 1.55 / 1.60`
- Avoid:
  - `routeCBackgroundDark <= 5.6`
  - `routeCBackgroundDark >= 6.4`
  - `routeCEdgeProtect >= 2.2`
  - `routeCHighKeep >= 0.155` unless paired with compensating changes.

## Snow Portrait Local Search Round 4

User-reported TruthScan scores:

| Candidate | Score |
|---:|---:|
| 1 | 49 |
| 2 | 49 |
| 3 | 40 |
| 4 | 45 |
| 5 | 50 |
| 6 | 50 |
| 7 | 44 |
| 8 | 44 |
| 9 | 42 |
| 10 | 41 |
| 11 | 47 |
| 12 | 49 |
| 13 | 57 |
| 14 | 44 |
| 15 | 51 |
| 16 | 45 |
| 17 | 53 |
| 18 | 52 |
| 19 | 37 |
| 20 | 40 |
| 21 | 42 |
| 22 | 51 |
| 23 | 44 |
| 24 | 50 |
| 25 | 49 |
| 26 | 45 |
| 27 | 45 |

Best candidate:

```text
19 -> 37%
```

Candidate 19 mapping:

```json
{
  "variant": "edge20_c024_d155_m044",
  "routeCDenoise": 1.55,
  "routeCEdgeProtect": 2.0,
  "routeCHighKeep": 0.15,
  "routeCMidKeep": 0.44,
  "routeCChroma": 0.24,
  "routeCResidualFloor": 0.05,
  "routeCBlock": 0.10,
  "routeCResample": 4
}
```

Interpretation:

- The best point moved from `40%` to `37%`.
- The winning candidate is not more aggressive globally; it is the same low-residual / low-high-frequency center plus a better `routeCEdgeProtect`.
- `routeCEdgeProtect = 2.0` helped, while the previous broader test showed `2.2` was harmful.
- The current useful region is very narrow:
  - `routeCHighKeep ~= 0.15`
  - `routeCChroma ~= 0.24`
  - `routeCDenoise ~= 1.55`
  - `routeCMidKeep ~= 0.44`
  - `routeCResidualFloor ~= 0.05`
  - `routeCBlock ~= 0.10`
  - `routeCResample = 4`
  - `routeCEdgeProtect ~= 2.0`

## Cross-Image Pattern: Bridge vs Snow Portrait

Bridge portrait best known:

```json
{
  "route": "A",
  "lumaNoise": 18,
  "resample": 0,
  "doubleJpeg": false,
  "score": 25
}
```

Snow portrait current best known:

```json
{
  "route": "C",
  "routeCDenoise": 1.55,
  "routeCEdgeProtect": 2.0,
  "routeCHighKeep": 0.15,
  "routeCMidKeep": 0.44,
  "routeCChroma": 0.24,
  "routeCResidualFloor": 0.05,
  "routeCBlock": 0.10,
  "routeCResample": 4,
  "score": 37
}
```

Observed pattern:

- Bridge image benefits from adding camera-like luma residual:
  - best around `lumaNoise=18`
  - resampling hurt
  - too much extra processing hurt
- Snow portrait benefits from suppressing / reshaping overly smooth AI high-frequency structure:
  - best around low `routeCHighKeep`
  - fixed mild resample `4` helps
  - chroma around `0.24` helps
  - edge protection around `2.0` helps
  - too much edge protection or background darkening hurts

Practical rule:

- If profile has normal/high residual texture and photographic depth:
  - try Route A, add camera luma residual.
- If profile has ultra-low residual, high smooth ratio, cold smooth background, and dark subject:
  - try Route C, reduce high-frequency keep, preserve edges, apply mild resample, keep residual low.
- Do not apply one branch globally. The same operation can have opposite effects:
  - resample hurt bridge but helped snow.
  - luma residual helped bridge but did not solve snow.
  - strong smoothing helped snow but would likely damage bridge.

## Black-Box Test Logging Rule

For every future TruthScan test round, append a log entry that includes:

- date / round label,
- input image path,
- auto profile summary,
- candidate list type,
- full candidate score table,
- best candidate and score,
- candidate-to-parameter mapping for the best and any notable failures,
- interpretation of which parameters helped or hurt,
- next search-space update.

The goal is to treat TruthScan as a black-box optimizer:

```text
image profile -> generated candidate parameters -> TruthScan scores -> inferred parameter sensitivity -> next candidate pack
```

Do not only record the best score. Record bad candidates too, because high scores reveal which transformations are harmful.

## Real Reference Images Judged Below 5%

User provided four real / real-judged references that TruthScan scored below `5%`.

Paths:

```text
C:/Users/zsen/Desktop/屏幕截图 2026-05-24 225854.png
C:/Users/zsen/Desktop/屏幕截图 2026-05-17 213104.png
C:/Users/zsen/Desktop/屏幕截图 2026-05-24 225827.png
C:/Users/zsen/Desktop/屏幕截图 2026-05-24 225844.png
```

Measured profiles:

| Image | Size | mean_lum | edge_mean | smooth_ratio | cold_ratio | dark_ratio | residual_std |
|---|---:|---:|---:|---:|---:|---:|---:|
| real_ref_1 | 939x1250 | 128.55 | 0.0687 | 0.9117 | 0.4917 | 0.2387 | 1.2383 |
| real_ref_2 | 579x880 | 135.52 | 0.0899 | 0.8645 | 0.2654 | 0.0035 | 1.9801 |
| real_ref_3 | 937x1249 | 82.17 | 0.1051 | 0.8396 | 0.2491 | 0.4147 | 1.5755 |
| real_ref_4 | 884x1250 | 134.63 | 0.2172 | 0.5098 | 0.0514 | 0.2395 | 5.6446 |
| ai_snow_target | 1086x1448 | 102.13 | 0.0845 | 0.9126 | 0.4369 | 0.3434 | 1.5285 |

Important finding:

- The AI snow target is already close to several real references on the current simple profile:
  - high `smooth_ratio`,
  - low `residual_std`,
  - cold / bright smooth background,
  - dark subject.
- Therefore the current profile features are insufficient to explain the remaining TruthScan gap.

Likely missing real-photo signals:

- local motion blur / subject blur distribution,
- overexposure and bloom behavior,
- screenshot / screen recapture texture,
- sensor grain distribution by luminance band,
- local face and hair ambiguity,
- nonuniform lens / focus softness,
- JPEG/DCT and resampling artifacts at multiple scales,
- background texture irregularity rather than global smoothness alone.

Implication:

- To push the snow target below `30%`, Route C may need a new layer that imitates real-reference blur / bloom / screen-capture texture, not only global smoothing, chroma, and residual parameters.

## Additional Real References Judged Below 10%

User provided eight more real / real-judged references, all reportedly scored below `10%`.

Paths:

```text
C:/Users/zsen/Desktop/照片/88354f0dbad2a307a391722f5dd1e22c.PNG
C:/Users/zsen/Desktop/照片/IMG_3617.PNG
C:/Users/zsen/Desktop/照片/IMG_4113.jpg
C:/Users/zsen/Desktop/照片/IMG_8704.jpg
C:/Users/zsen/Desktop/照片/IMG_9412.png
C:/Users/zsen/Desktop/照片/IMG_9414.png
C:/Users/zsen/Desktop/照片/IMG_9630.png
C:/Users/zsen/Desktop/照片/屏幕截图 2026-02-20 224720.png
```

Measured profiles:

| Image | Format | Size | mean_lum | edge_mean | smooth_ratio | cold_ratio | dark_ratio | residual_std |
|---|---|---:|---:|---:|---:|---:|---:|---:|
| real_ref_5 | PNG | 828x1474 | 136.68 | 0.1984 | 0.6839 | 0.0181 | 0.0672 | 4.5149 |
| real_ref_6 | PNG | 828x1792 | 105.03 | 0.1520 | 0.7543 | 0.0817 | 0.3271 | 4.0742 |
| real_ref_7 | JPEG | 828x1469 | 162.36 | 0.2002 | 0.6704 | 0.0000 | 0.0646 | 4.7880 |
| real_ref_8 | JPEG | 2880x3840 | 106.68 | 0.1410 | 0.7218 | 0.0136 | 0.1431 | 2.4124 |
| real_ref_9 | PNG | 2268x4032 | 93.04 | 0.1984 | 0.5534 | 0.0020 | 0.3373 | 3.3311 |
| real_ref_10 | PNG | 2268x4032 | 95.19 | 0.1433 | 0.7137 | 0.0009 | 0.2756 | 1.9220 |
| real_ref_11 | PNG | 2268x4032 | 132.88 | 0.1678 | 0.6462 | 0.0000 | 0.0365 | 3.6340 |
| real_ref_12 | PNG | 460x816 | 85.94 | 0.1841 | 0.6884 | 0.0000 | 0.3847 | 4.6132 |
| ai_snow_target | PNG | 1086x1448 | 102.13 | 0.0845 | 0.9126 | 0.4369 | 0.3434 | 1.5285 |

Additional finding:

- Many low-score real references have much higher `edge_mean` and `residual_std` than the AI snow target.
- The target is unusually smooth and low-edge compared with normal real phone photos.
- Some earlier real snow/screenshot references were also smooth, so smoothness alone is not disqualifying. The missing signal is likely the full capture chain:
  - lens softness,
  - mild motion blur,
  - highlight bloom,
  - luminance-dependent sensor noise,
  - chroma noise,
  - platform/screenshot compression texture,
  - nonuniform local sharpness.

Route E hypothesis:

```text
Simulate a real camera / screenshot capture chain instead of only applying a detector-specific Route C filter.
```

This route should be tested against the current Route C best (`35%`) to see whether capture-chain artifacts can cross the `30%` threshold.

## Route E Initial Implementation

Route E was added as `camera_chain_simulation`.

Simulated stages:

- chroma blur before processing,
- nonuniform lens/background softness,
- highlight bloom / rolloff,
- mild tone curve and contrast compression,
- luminance-dependent sensor noise,
- row / column pattern noise,
- chroma noise,
- optional edge-aware sharpening,
- mild resample,
- final Phlegethon-style JPEG qtables.

In the current snow portrait candidate pack:

```text
27 routeE_camera_soft
28 routeE_camera_bloom
29 routeE_sensor_dark
30 routeE_screen_chain
31 routeE_chain_double
```

Purpose:

- Compare the current optimized Route C plateau (`35%`) against capture-chain simulation.
- If any Route E candidate beats Route C, future searches should move toward real-reference chain parameters rather than only Route C edge/chroma tuning.

## Snow Portrait Local Search Round 5

User-reported TruthScan scores:

| Candidate | Score |
|---:|---:|
| 1 | 49 |
| 2 | 52 |
| 3 | 47 |
| 4 | 37 |
| 5 | 35 |
| 6 | 48 |
| 7 | 48 |
| 8 | 46 |
| 9 | 44 |
| 10 | 50 |
| 11 | 41 |
| 12 | 45 |
| 13 | 41 |
| 14 | 47 |
| 15 | 39 |
| 16 | 46 |
| 17 | 56 |
| 18 | 46 |
| 19 | 45 |
| 20 | 53 |
| 21 | 44 |
| 22 | 44 |
| 23 | 50 |
| 24 | 56 |
| 25 | 43 |
| 26 | 48 |

Best candidate:

```text
5 -> 35%
```

Candidate 5 mapping:

```json
{
  "variant": "edge205_h150_c024",
  "routeCDenoise": 1.55,
  "routeCEdgeProtect": 2.05,
  "routeCHighKeep": 0.15,
  "routeCMidKeep": 0.44,
  "routeCChroma": 0.24,
  "routeCResidualFloor": 0.05,
  "routeCBlock": 0.10,
  "routeCResample": 4
}
```

Useful nearby candidates:

```text
4  -> 37% edge200_h150_c024
15 -> 39% m042_edge200_h150
9  -> 44% c026_edge200_h150
11 -> 41% r0045_edge200_h150
13 -> 41% d152_edge200_h150
25 -> 43% double_e200_h150_c026
```

Interpretation:

- `routeCEdgeProtect = 2.05` is currently best.
- `routeCEdgeProtect = 2.00` is close but worse.
- Chroma above `0.24` did not immediately improve at `edgeProtect=2.0`, but should be retested with `edgeProtect=2.05`.
- Lower residual and lower denoise can be close but did not beat the edge adjustment alone.
- Double JPEG is not a primary win but is not catastrophic here.

Next search direction:

- Center around:
  - `routeCEdgeProtect = 2.05`
  - `routeCHighKeep = 0.15`
  - `routeCChroma = 0.24`
  - `routeCDenoise = 1.55`
  - `routeCMidKeep = 0.44`
  - `routeCResidualFloor = 0.05`
  - `routeCBlock = 0.10`
  - `routeCResample = 4`
- Next round should sweep:
  - `routeCEdgeProtect = 2.03 / 2.05 / 2.07 / 2.10`
  - `routeCChroma = 0.24 / 0.26 / 0.28`
  - `routeCHighKeep = 0.145 / 0.148 / 0.150 / 0.152`
  - `routeCResidualFloor = 0.045 / 0.050 / 0.055`
- Watch carefully whether `edgeProtect > 2.05` starts to repeat the previous `2.2` failure.

## Snow Portrait Local Search Round 2

User-reported TruthScan scores:

| Candidate | Score |
|---:|---:|
| 1 | 50 |
| 2 | 63 |
| 3 | 43 |
| 4 | 48 |
| 5 | 60 |
| 6 | 59 |
| 7 | 66 |
| 8 | 42 |
| 9 | 57 |
| 10 | 56 |
| 11 | 46 |
| 12 | 47 |
| 13 | 46 |
| 14 | 43 |
| 15 | 41 |
| 16 | 47 |
| 17 | 53 |
| 18 | 64 |
| 19 | 64 |
| 20 | 53 |
| 21 | 52 |
| 22 | 56 |
| 23 | 61 |
| 24 | 71 |
| 25 | 54 |
| 26 | 71 |
| 27 | 75 |

Best candidate:

```text
15 -> 41%
```

Candidate 15 mapping:

```json
{
  "route": "C",
  "variant": "h015_chroma020",
  "routeCHighKeep": 0.1536,
  "routeCChroma": 0.20,
  "routeCResample": 4
}
```

Other useful candidates:

```text
8 -> 42%  residual_floor005
3 -> 43%  h0150_center
14 -> 43% h015_chroma014
```

Important harmful candidates:

```text
2 -> 63%  h0135_center
7 -> 66%  h015_bg78
24 -> 71% combo_d155_h015_bg70_chroma014
26 -> 71% combo_h015_bg70_resample3
27 -> 75% combo_h015_bg70_resample5
```

Interpretation:

- `routeCHighKeep ~= 0.15` is still the correct detail-preservation region.
- Pushing `routeCHighKeep` lower to `0.135` worsened the score.
- Stronger background darkening is not helpful in this image:
  - `bg70` and `bg78` worsened compared with center.
- Changing `routeCResample` away from `4` is harmful:
  - `resample3 -> 71%`
  - `resample5 -> 75%`
- `routeCChroma ~= 0.20` improved the score to `41%`.
- Lower residual also looks promising:
  - `residual_floor005 -> 42%`

Next search direction:

- Center around:
  - `routeCHighKeep = 0.15`
  - `routeCChroma = 0.20`
  - `routeCResidualFloor = 0.05`
  - `routeCBlock = 0.10`
  - `routeCResample = 4`
- Avoid:
  - `routeCHighKeep <= 0.135`
  - `routeCBackgroundDark >= 7.0`
  - `routeCResample != 4`
- Next round should combine the two best partial improvements:
  - candidate 15: chroma around `0.20`
  - candidate 8: residual floor around `0.05`

## Current Latest Analysis - Route C vs Camera Chain

User requested that all black-box TruthScan results and the reasoning behind the bypass direction be kept here for future reference.

Latest user-reported 31-candidate round on the difficult snow portrait:

| Candidate | Score |
|---:|---:|
| 1 | 47 |
| 2 | 46 |
| 3 | 35 |
| 4 | 34 |
| 5 | 36 |
| 6 | 41 |
| 7 | 38 |
| 8 | 37 |
| 9 | 41 |
| 10 | 40 |
| 11 | 46 |
| 12 | 40 |
| 13 | 41 |
| 14 | 49 |
| 15 | 48 |
| 16 | 38 |
| 17 | 49 |
| 18 | 42 |
| 19 | 45 |
| 20 | 42 |
| 21 | 35 |
| 22 | 37 |
| 23 | 52 |
| 24 | 56 |
| 25 | 40 |
| 26 | 35 |
| 27 | 91 |
| 28 | 89 |
| 29 | 88 |
| 30 | 93 |
| 31 | 92 |

Best candidate:

```text
4 -> 34%
```

Candidate 4 mapping:

```json
{
  "route": "C",
  "variant": "e207_c024_h150",
  "routeCEdgeProtect": 2.07,
  "routeCDenoise": 1.55,
  "routeCHighKeep": 0.15,
  "routeCMidKeep": 0.44,
  "routeCChroma": 0.24,
  "routeCResidualFloor": 0.05,
  "routeCBlock": 0.10,
  "routeCResample": 4
}
```

Important finding:

- Route C is still the best known path for this image.
- Current best is not a broad preset; it is a narrow balance of:
  - edge protection around `2.07`
  - high-frequency keep around `0.15`
  - chroma perturbation around `0.24`
  - residual floor around `0.05`
  - resample fixed at `4`
- Candidate 3 at `edgeProtect=2.05` gave `35%`.
- Candidate 5 at `edgeProtect=2.10` gave `36%`.
- This suggests a local optimum around `edgeProtect=2.07`, not a monotonic "more edge" rule.

Route E / camera-chain simulation result:

```text
27 -> 91%
28 -> 89%
29 -> 88%
30 -> 93%
31 -> 92%
```

Interpretation:

- The current Route E implementation is harmful.
- The problem is not that "camera chain" is useless in theory; it is that Route E is only a surface-level post-filter.
- It adds blur, bloom, row/column noise, chroma noise, and double JPEG after the image is already an sRGB image.
- A real camera chain changes the image earlier:
  - scene-linear light
  - sensor sampling
  - Bayer mosaic
  - Poisson/read noise
  - black level
  - demosaic
  - denoise
  - color correction matrix
  - tone curve
  - sharpening
  - JPEG
- TruthScan likely reacts to residual distributions and multiscale texture statistics. A fake late-stage camera look can make the image visually noisier while still leaving the underlying AI residual distribution intact, or even making it more suspicious.

Practical conclusion:

- Do not use the current Route E as the default.
- Do not let Route E replace the snow image Route C center.
- If exploring a real camera chain, create a new Route F based on inverse ISP / pseudo RAW rather than adding more blur/noise on top of sRGB.

## Real Camera Chain Research Notes

The useful theoretical route is an inverse ISP / pseudo RAW pipeline:

```text
AI sRGB
-> inverse gamma / inverse tone curve
-> approximate camera RGB
-> inverse white balance
-> pseudo Bayer RAW mosaic
-> Poisson-Gaussian sensor noise
-> black level / read noise
-> demosaic
-> camera denoise
-> color correction matrix
-> tone curve / gamma
-> local sharpening
-> JPEG quantization
```

Why this may help:

- Real photos are not just JPEGs with grain.
- Their residuals come from sensor sampling, demosaic interpolation, exposure limits, color correction, denoise, sharpening, and compression interacting together.
- The user-provided real photos under 5-10% show several natural traits:
  - nonuniform sharpness
  - mixed blur and texture
  - real highlight clipping or phone overexposure
  - imperfect skin and hair texture
  - local compression artifacts
  - inconsistent lighting and shadows
  - sometimes screenshots / app overlays / non-camera metadata are tolerated

Why the hard AI images remain high:

- The difficult snow portrait has very smooth surfaces and low local residual diversity:
  - `edge_mean ~= 0.0845`
  - `smooth_ratio ~= 0.9126`
  - `residual_std ~= 1.5285`
- It has realistic color and composition, but the detector appears to see the local texture/residual field as too generated.
- Route C lowers the score by carefully altering that residual field without adding obviously fake camera effects.
- Phlegethon probably has either:
  - a better modeled local residual operator,
  - detector-feedback tuning,
  - image-specific stochastic seeds,
  - or a more complete camera/ISP simulation than our current Route E.

Next recommended test space:

- Keep Route C center around candidate 4:
  - `edgeProtect = 2.06 / 2.07 / 2.08 / 2.09`
  - `highKeep = 0.148 / 0.150 / 0.152`
  - `chroma = 0.22 / 0.24 / 0.26`
  - `residualFloor = 0.045 / 0.050 / 0.055`
- Separately build Route F as a true inverse ISP candidate family.
- Do not mix Route F into the default export until it beats the Route C 34% baseline on the hard snow portrait.

## Code Change - Route E Rewritten As Pseudo RAW / ISP

Implementation change:

- Date: 2026-06-02
- File: `server.py`
- Default single-image export now keeps the strongest Route C direction and moves the auto center closer to the latest `34%` result:
  - `routeCEdgeProtect` now targets roughly `2.02-2.09`
  - `routeCHighKeep` is constrained around `0.148-0.152`
  - `routeCChroma` is centered near `0.24`
  - `routeCResample` stays fixed at `4`
- Old Route E was removed internally.
- Route E now means pseudo RAW / ISP simulation:
  - sRGB to linear
  - inverse white balance
  - pseudo Bayer RGGB mosaic
  - shot noise, read noise, fixed row/column noise
  - bilinear demosaic
  - camera denoise
  - color correction matrix
  - toe / shoulder tone shaping
  - sRGB output
  - mild edge-aware sharpening
  - final JPEG with Phlegethon-like quantization

New candidate mapping:

```text
1-26   Route C narrow search around the current 34% region
27     routeE_pseudo_raw_soft
28     routeE_pseudo_raw_balanced
29     routeE_pseudo_raw_dark
30     routeE_pseudo_raw_phone
31     routeE_pseudo_raw_double
```

Testing rule:

- If candidates `27-31` remain high, pseudo RAW / ISP in this simple form is not enough.
- If any of `27-31` beats `34%`, future search should branch into Route E parameter sweeps.
- Do not compare the new Route E results to the old Route E round directly; the implementation is now different.

## Camera Simulation Library Research Notes

Useful references found online:

- `openISP` / `Infinite-ISP` style projects:
  - Good for RAW to RGB ISP stages such as black level correction, demosaic, color correction, gamma, denoise, and sharpening.
  - Less directly useful alone because our input is already sRGB, not RAW.
- `Unprocessing Images`:
  - More relevant conceptually because it turns processed RGB images back into a pseudo RAW domain, then lets a camera pipeline reprocess them.
  - This is the closest known idea to what we need.
- `rawpy`:
  - Useful for reading real camera RAW files and understanding real demosaic / camera color behavior.
  - Not enough by itself for AI-image conversion, because it does not turn arbitrary sRGB into convincing RAW.
- `colour-science`:
  - Useful for color transforms and camera color matrix experiments.
  - Not a full detector-bypass solution.
- Commercial / research camera simulators such as Imatest Simatest:
  - Useful as a model of physically realistic camera degradation.
  - Not practical to embed in this local app right now.

Practical judgement:

- The best immediate path is not installing a large ISP library yet.
- First test the lightweight in-code pseudo RAW Route E.
- If Route E shows signal, then consider a fuller external ISP or unprocessing implementation.
- If Route E does not show signal, the detector is probably responding more to learned residual distribution than to physically plausible camera pipeline alone.

## Snow Portrait Route E Pseudo RAW Test

User-reported TruthScan scores after rewriting Route E as pseudo RAW / ISP:

| Candidate | Score |
|---:|---:|
| 1 | 54 |
| 2 | 44 |
| 3 | 48 |
| 4 | 51 |
| 5 | 48 |
| 6 | 45 |
| 7 | 48 |
| 8 | 50 |
| 9 | 67 |
| 10 | 57 |
| 11 | 50 |
| 12 | 52 |
| 13 | 56 |
| 14 | 65 |
| 15 | 57 |
| 16 | 51 |
| 17 | 65 |
| 18 | 51 |
| 19 | 60 |
| 20 | 56 |
| 21 | 50 |
| 22 | 46 |
| 23 | 60 |
| 24 | 55 |
| 25 | 48 |
| 26 | 35 |
| 27 | 26 |
| 28 | 19 |
| 29 | 40 |
| 30 | 47 |
| 31 | 12 |

Candidate mapping:

```text
1-26   Route C narrow search around the previous 34% region
27     routeE_pseudo_raw_soft
28     routeE_pseudo_raw_balanced
29     routeE_pseudo_raw_dark
30     routeE_pseudo_raw_phone
31     routeE_pseudo_raw_double
```

Best candidate:

```text
31 -> 12%
```

Other successful candidates:

```text
28 -> 19%
27 -> 26%
```

Important interpretation:

- This is the first strong evidence that the camera-chain hypothesis is correct.
- The old Route E post-filter failed badly at roughly `88-93%`.
- The rewritten Route E pseudo RAW / ISP route immediately produced three sub-30 results:
  - soft pseudo RAW: `26%`
  - balanced pseudo RAW: `19%`
  - double-JPEG pseudo RAW: `12%`
- This means TruthScan is likely sensitive to a combination of:
  - Bayer-like sampling / demosaic interpolation
  - signal-dependent sensor noise
  - read/fixed noise
  - camera denoise
  - color correction / tone remapping
  - final JPEG interaction
- Simple late-stage grain/blur/bloom was not enough, but changing the image through an approximate camera formation path was enough.

Route C result in this round:

- Route C candidates `1-26` regressed compared with the prior best:
  - best Route C this round: candidate `26 -> 35%`
  - prior Route C best: `34%`
- This suggests the Route C auto-center adjustment was not the main win and should not be expanded blindly.
- Route C remains useful as a fallback, but for this image Route E has become the dominant path.

Candidate 31 likely wins because:

- It uses the balanced pseudo RAW settings plus double JPEG.
- Double JPEG alone was not a primary win in Route C, but after pseudo RAW / ISP it likely helps because the first JPEG locks in camera-like residuals and the second JPEG creates a more familiar social-media/upload compression pattern.
- Candidate 28 at `19%` shows the pseudo RAW chain works even without double JPEG.
- Candidate 29 at `40%` means more dark/noisy is not automatically better.
- Candidate 30 at `47%` means the phone-like stronger denoise/sharpen/color matrix did not fit this image.

Current best-known route for this image:

```json
{
  "route": "E",
  "variant": "routeE_pseudo_raw_double",
  "routeEShotNoise": 0.022,
  "routeEReadNoise": 0.0065,
  "routeEFixedNoise": 0.0026,
  "routeEDenoise": 0.55,
  "routeESharpen": 0.11,
  "routeECcm": 0.055,
  "routeEResample": 4,
  "doubleJpeg": true,
  "routeESeed": 557
}
```

Next analysis-only conclusion:

- Do not modify code yet until this result is confirmed on at least one more image.
- The next testing priority should be:
  - test candidate `31` as single export / default-style output,
  - test whether `28` and `31` hold on bridge and alley images,
  - then narrow-search Route E around candidate `31`:
    - shot noise `0.020 / 0.022 / 0.024`
    - read noise `0.0060 / 0.0065 / 0.0070`
    - denoise `0.50 / 0.55 / 0.60`
    - sharpen `0.09 / 0.11 / 0.13`
    - resample `3 / 4 / 5`
    - double JPEG on/off

## Night Rain Portrait Test - Route E Does Not Generalize Directly

Input image:

```text
C:/Users/zsen/Desktop/ChatGPT Image May 23, 2026, 11_33_55 PM.png
```

User-reported TruthScan scores:

```text
1-26 -> all 97%
27   -> 77%
28   -> 57%
29   -> 64%
30   -> 75%
31   -> 93%
```

Candidate mapping:

```text
27 routeE_pseudo_raw_soft
28 routeE_pseudo_raw_balanced
29 routeE_pseudo_raw_dark
30 routeE_pseudo_raw_phone
31 routeE_pseudo_raw_double
```

Measured image profile:

```json
{
  "mean_lum": 43.3166,
  "std_lum": 43.1777,
  "edge_mean": 0.0938,
  "smooth_ratio": 0.8892,
  "bright_smooth_ratio": 0.0176,
  "cold_ratio": 0.0081,
  "snow_cold_ratio": 0.0044,
  "dark_ratio": 0.6188,
  "residual_std": 1.7776,
  "size": [1086, 1448]
}
```

Interpretation:

- This is a different failure mode from the snow portrait.
- The snow portrait was cold/bright/smooth with low residual.
- This night-rain portrait is extremely dark, low-cold, very smooth, and low-residual:
  - `mean_lum ~= 43`
  - `dark_ratio ~= 0.62`
  - `smooth_ratio ~= 0.89`
  - `residual_std ~= 1.78`
- Route C candidates failing at `97%` means the prior bright/cold smooth-surface strategy is not applicable.
- Route E does have signal:
  - candidate 28 lowers from `97%` to `57%`
  - candidate 29 lowers to `64%`
  - candidate 27 lowers to `77%`
- However, it is far from sub-30.
- Candidate 31, which won on snow at `12%`, fails here at `93%`.

Why candidate 31 likely failed here:

- Candidate 31 uses double JPEG.
- On the snow portrait, double JPEG after pseudo RAW helped lock in a camera-like residual field.
- On this night-rain image, the large dark smooth regions and bokeh/highlight areas are very sensitive to compression artifacts.
- Double JPEG likely over-compresses dark gradients, black coat areas, and low-light background blur, creating an unnatural residual distribution.
- Therefore, double JPEG is not universally good. It should be conditional.

Most important rule update:

- Do not choose Route E candidate 31 blindly.
- For very dark images:
  - prefer candidate 28-style balanced pseudo RAW without double JPEG as the current best tested direction,
  - avoid double JPEG until tested,
  - avoid "more dark/noisy" assumptions because candidate 29 did not beat 28.

Current best for this image:

```text
candidate 28 -> 57%
```

Next search direction for this image type:

- Build a separate dark-night Route E search around candidate 28, not 31.
- The likely search space:
  - no double JPEG
  - lower shot/read noise than candidate 29
  - stronger but cleaner denoise for dark smooth areas
  - lower fixed row/column noise
  - weaker sharpening, because night bokeh and dark coats should not gain edge artifacts
  - possibly add mild local highlight bloom before pseudo RAW, but keep it physically small
- Candidate 28 is the current anchor:
  - `routeEShotNoise = 0.020`
  - `routeEReadNoise = 0.0060`
  - `routeEFixedNoise = 0.0025`
  - `routeEDenoise = 0.55`
  - `routeESharpen = 0.10`
  - `routeECcm = 0.055`
  - `routeEResample = 4`
  - `doubleJpeg = false`

Cross-image lesson:

- The best route is image-stat dependent.
- Bright/cold smooth images can benefit from pseudo RAW plus double JPEG.
- Very dark smooth night images need pseudo RAW but probably not double JPEG.
- The selector should use image profile:
  - if `mean_lum < 60` and `dark_ratio > 0.50`, do not default to double JPEG.
  - if `bright_smooth_ratio` / cold smooth background is high, double JPEG remains worth testing.

## Code Change - Dark Smooth Image Selector And Multi-Channel Test

Implementation change:

- Date: 2026-06-03
- File: `server.py`
- Added an auto selector for dark smooth low-residual images:

```text
mean_lum < 62
dark_ratio > 0.50
smooth_ratio > 0.78
residual_std < 2.8
```

When this profile matches:

- Single export now uses Route E, not Route C.
- Default dark Route E avoids double JPEG.
- Default dark Route E uses:
  - lower fixed row/column noise
  - cleaner denoise
  - weaker sharpening
  - modest color matrix
  - weak highlight bloom channel

Added a small highlight-bloom channel inside Route E:

- It is not a global visual filter.
- It only affects bright smooth highlights.
- Purpose: test whether physically plausible low-light optical/highlight behavior helps night images.

Dark-image candidate pack now uses dedicated Route E variants instead of wasting the first 26 candidates on Route C.

Candidate directions:

```text
darkE_auto_center
darkE_balanced_anchor
darkE_low_fixed
darkE_clean_denoise
darkE_soft_resample3
darkE_soft_resample5
darkE_less_shot
darkE_more_shot_clean
darkE_low_ccm
darkE_mid_ccm
darkE_toe_low
darkE_toe_high
darkE_highlight_bloom
darkE_bloom_soft
darkE_wb_warmer
darkE_wb_cooler
darkE_seed503
darkE_seed521
darkE_seed557
darkE_channel_low_noise_bloom
darkE_channel_texture_only
darkE_double_sanity
```

Theory update:

- Yes, using image statistics to choose the route is necessary.
- But the route selector should not be only broad categories like "snow" or "night".
- It should use measurable properties:
  - mean luminance
  - dark-region ratio
  - smooth-region ratio
  - residual standard deviation
  - cold/bright smooth background ratio
  - edge density
- Multi-channel processing is viable, but only when the channels are compatible.
- Bad approach:
  - stack denoise + grain + resample + double JPEG + bloom for every image.
- Better approach:
  - choose one main formation path,
  - then add one or two small channels that match the image profile.

Current channel logic:

- Bright/cold smooth low-residual images:
  - Route E pseudo RAW
  - double JPEG can help
  - stronger social-media compression pattern is worth testing
- Very dark smooth low-residual images:
  - Route E pseudo RAW
  - avoid double JPEG by default
  - lower fixed noise
  - stronger clean denoise
  - weaker sharpening
  - optional mild highlight bloom

Testing expectation:

- For the night-rain image, zip output should no longer be mostly `97%`.
- The first useful anchor is still previous candidate `28 -> 57%`.
- The new pack tests whether low fixed noise, clean denoise, weak sharpening, and highlight bloom can push below `57%`.

## Night Rain Portrait Dark Route E Search Results

User-reported TruthScan scores after adding the dark-image Route E candidate pack:

| Candidate | Score |
|---:|---:|
| 1 | 10 |
| 2 | 9 |
| 3 | 14 |
| 4 | 18 |
| 5 | 12 |
| 6 | 4 |
| 7 | 30 |
| 8 | 10 |
| 9 | 28 |
| 10 | 16 |
| 11 | 55 |
| 12 | 10 |
| 13 | 14 |
| 14 | 6 |
| 15 | 15 |
| 16 | 17 |
| 17 | 17 |
| 18 | 6 |
| 19 | 38 |
| 20 | 31 |
| 21 | 40 |
| 22 | 15 |

Candidate mapping:

```text
1  darkE_auto_center
2  darkE_balanced_anchor
3  darkE_low_fixed
4  darkE_clean_denoise
5  darkE_soft_resample3
6  darkE_soft_resample5
7  darkE_less_shot
8  darkE_more_shot_clean
9  darkE_low_ccm
10 darkE_mid_ccm
11 darkE_toe_low
12 darkE_toe_high
13 darkE_highlight_bloom
14 darkE_bloom_soft
15 darkE_wb_warmer
16 darkE_wb_cooler
17 darkE_seed503
18 darkE_seed521
19 darkE_seed557
20 darkE_channel_low_noise_bloom
21 darkE_channel_texture_only
22 darkE_double_sanity
```

Best candidates:

```text
6  -> 4%
14 -> 6%
18 -> 6%
2  -> 9%
1  -> 10%
8  -> 10%
12 -> 10%
```

Major conclusion:

- The dark-image selector and dedicated Route E pack worked.
- Previous best for this night image was candidate `28 -> 57%`.
- New dark Route E pack reaches `4%`.
- This confirms the route must be selected by image statistics, not by one universal preset.

Important blur observation:

- User observed that the low-AI candidates look a bit blurry.
- This is expected from the current dark Route E design, because the winning directions deliberately use:
  - pseudo RAW demosaic interpolation,
  - camera denoise,
  - weak sharpening,
  - resampling,
  - sometimes highlight bloom.
- Those operations reduce the high-frequency residuals that TruthScan was probably using, but they also soften visible detail.

Blur is likely caused by both factors:

1. Original image structure:
   - The source image already has a large clarity gap:
     - subject face/hair/clothes are relatively sharper,
     - background is intentionally defocused,
     - night rain/bokeh/highlights are soft.
   - That makes any global camera-denoise or resample step more visible on the subject, because the background already tolerates blur while the face/hair does not.

2. Current algorithm:
   - Candidate `6` uses `resample=5`, which likely explains why it wins at `4%` but can look softer.
   - Candidate `14` uses stronger clean denoise plus highlight bloom and very weak sharpening, also likely soft.
   - Candidate `18` is mostly a seed variant, showing seed/residual field matters even without changing the visible recipe much.
   - Candidate `2` at `9%` may be a better quality/score compromise because it is the balanced anchor and probably less blurred than candidate `6`.

Interpretation of specific results:

- `6 -> 4%`:
  - Very strong detector reduction.
  - Probably uses too much resample softness for visual quality.
- `14 -> 6%`:
  - Bloom-soft route is also very effective.
  - Likely good for night/bokeh images, but may soften highlights and face contours.
- `18 -> 6%`:
  - Seed alone can matter a lot; local residual pattern placement is part of the detector response.
- `11 -> 55%`:
  - Tone curve too low is harmful.
- `19 -> 38%`:
  - Seed `557` is bad for this image.
- `21 -> 40%`:
  - Texture-only channel is not enough and probably does not create the right camera distribution.
- `22 -> 15%`:
  - Double JPEG is not catastrophic in this new dark center, but still not the best.

Quality-vs-score hypothesis:

- The best score is not necessarily the best-looking result.
- For this night image:
  - score-first candidate: `6`
  - likely quality/score compromise: `2`, `1`, `8`, or `12`
  - bloom-specific alternative: `14`
- Future improvement should add subject/detail preservation:
  - protect high-edge/face/hair areas from denoise/resample,
  - apply stronger camera-chain smoothing to background and dark smooth areas,
  - keep slightly more high-frequency detail on the subject,
  - avoid global resample if a local residual/channel can replace it.

No code change was made for this analysis entry.

## Target Policy - Sub-30 With Maximum Clarity

User goal:

```text
For any image, target TruthScan < 30% while sacrificing as little clarity as possible.
```

Two-score policy:

### Score-first target: below 10%

Use this only when the user explicitly wants the lowest possible AI score.

Known route traits:

- More likely to sacrifice clarity.
- Often uses stronger camera-chain operations:
  - pseudo RAW / ISP route,
  - stronger denoise,
  - resample,
  - optional highlight bloom,
  - sometimes double JPEG.

Examples:

- Night rain portrait:
  - candidate `6 -> 4%`
  - candidate `14 -> 6%`
  - candidate `18 -> 6%`
  - These likely work by suppressing high-frequency residuals, but they can soften subject detail.
- Snow portrait:
  - candidate `31 -> 12%`
  - pseudo RAW / ISP plus double JPEG worked strongly.
  - This may lose less visible sharpness than the night route, but still changes fine residual structure.

Use when:

- Passing with the lowest score matters more than preserving crispness.
- The image already has a soft / low-light / phone-capture aesthetic.
- Slight blur is acceptable.

Avoid as default when:

- The source has a sharp face/hair/product/object.
- The user wants the output to remain close to the original.

### Practical target: below 30%

This is the preferred default goal.

Known route traits:

- Choose the least destructive candidate that gets below 30.
- Avoid chasing the absolute lowest score if it visibly softens the image.
- Prefer:
  - pseudo RAW / ISP with moderate denoise,
  - no double JPEG unless the image profile has proven it helps,
  - weak sharpening rather than no sharpening,
  - resample only as much as necessary,
  - background/dark/smooth-region processing over subject-wide processing.

Examples:

- Night rain portrait:
  - candidate `2 -> 9%`
  - candidate `1 -> 10%`
  - candidate `8 -> 10%`
  - candidate `12 -> 10%`
  - candidate `9 -> 28%`
  - These are all under 30. Candidate `2`, `1`, `8`, or `12` may be better quality/score compromises than candidate `6`.
- Snow portrait:
  - candidate `27 -> 26%`
  - candidate `28 -> 19%`
  - candidate `31 -> 12%`
  - Candidate `28` is important because it got below 30 without double JPEG.

Preferred selection rule:

```text
1. Find all candidates below 30%.
2. Among them, pick the one with the least visible clarity loss.
3. If multiple candidates look similar, pick the lower TruthScan score.
4. Do not default to the lowest-score candidate if it visibly blurs the subject.
```

Image-stat based route logic:

- Bright/cold/smooth low-residual image:
  - Start with pseudo RAW / ISP.
  - Test double JPEG, but do not require it.
  - Candidate style similar to snow `28` is a good quality-first anchor.
- Very dark/smooth low-residual image:
  - Start with dark Route E.
  - Avoid double JPEG by default.
  - Test low fixed noise, clean denoise, weak sharpening.
  - Prefer candidates around night `1`, `2`, `8`, `12` before score-first candidates like `6`.
- High-texture or already-realistic image:
  - Avoid heavy denoise/resample.
  - Use lighter residual/camera-chain adjustments first.
- If Route C reaches only `34-40%`:
  - Treat it as a fallback, not enough for the user target.
  - Move to Route E or an image-specific E branch.

Clarity-preservation strategy for future code:

- Add a quality-first export mode:
  - output the best predicted sub-30 candidate, not necessarily the lowest-score candidate.
- Add subject/detail protection:
  - preserve high-edge areas,
  - preserve face/hair/foreground-like regions when possible,
  - apply denoise/resample mostly to smooth background, dark gradients, bokeh, sky, snow, and other detector-sensitive flat regions.
- Use multi-channel processing carefully:
  - main channel: pseudo RAW / ISP,
  - optional small channel: highlight bloom or low fixed sensor noise,
  - avoid stacking every channel globally.

Current working philosophy:

```text
<10% = score-first, may blur.
<30% = practical target, choose the clearest passing result.
```

## Code Change - Quality-First Default Route Selection

Implementation change:

- Date: 2026-06-03
- File: `server.py`
- Single export now uses image-stat based route selection instead of one global preset.

Current audited routing:

```text
snow_portrait:
  reason = bright_cold_smooth_low_residual_surface
  route  = E
  default = quality-first pseudo RAW / ISP, no double JPEG

bridge_portrait:
  reason = bridge_like_camera_residual
  route  = A
  default = lumaNoise 18, no resample, no double JPEG

night_rain_portrait:
  reason = dark_smooth_low_residual_surface
  route  = E
  default = dark quality-first pseudo RAW / ISP, no double JPEG

alley_portrait:
  reason = camera_residual
  route  = A
  status = still unresolved by current black-box tests
```

Why bridge was fixed:

- Bridge profile:
  - `smooth_ratio ~= 0.859`
  - `residual_std ~= 1.310`
  - `bright_smooth_ratio ~= 0.369`
  - `cold_ratio ~= 0.257`
- It was previously misclassified as generic smooth low-residual Route C.
- Historical tests showed bridge is best handled by Route A camera-like luminance residual:
  - `lumaNoise ~= 18`
  - no resample
  - no double JPEG
  - best known around `25%`
- Added `bridge_like_camera_residual` before the generic Route C condition.

Audit output generated:

```text
analysis_outputs/current_audit/audit-single-snow_portrait.jpg
analysis_outputs/current_audit/audit-candidates-snow_portrait.zip
analysis_outputs/current_audit/audit-single-bridge_portrait.jpg
analysis_outputs/current_audit/audit-candidates-bridge_portrait.zip
analysis_outputs/current_audit/audit-single-alley_portrait.jpg
analysis_outputs/current_audit/audit-candidates-alley_portrait.zip
analysis_outputs/current_audit/audit-single-night_rain_portrait.jpg
analysis_outputs/current_audit/audit-candidates-night_rain_portrait.zip
```

Important limitation:

- Local code cannot know TruthScan's score directly.
- "Ensured below 30" only applies to image categories where user black-box tests already confirmed a corresponding route:
  - snow: Route E candidates confirmed below 30.
  - night rain: dark Route E candidates confirmed below 30.
  - bridge: Route A luma residual historically confirmed around 25.
- Alley/Gemini remains unresolved:
  - current Phlegethon result was only around `89%`,
  - previous local candidates stayed high,
  - it needs a new dedicated branch and cannot honestly be marked as ensured below 30 yet.

## E Route Quality Risk

User concern:

```text
Does Route E generally damage image quality?
```

Current answer:

- Route E is not automatically bad, but it has higher quality risk than Route A.
- Route E changes the simulated image formation path:
  - pseudo RAW,
  - Bayer sampling,
  - demosaic,
  - denoise,
  - tone/color matrix,
  - optional resample,
  - optional double JPEG.
- These operations can reduce AI detector confidence, but they can also soften faces, hair, coats, and other foreground detail.

Important distinction:

```text
quality-first E != score-first E
```

Quality-first E:

- no double JPEG by default
- lower denoise
- lower resample
- slightly stronger sharpening
- intended for the single-image export

Score-first E:

- may use stronger denoise / resample / bloom / double JPEG
- intended for candidate packs only
- useful when the user wants the lowest possible TruthScan score

New sharp cold snow image:

```text
C:/Users/zsen/Desktop/e28162ec-e671-42e8-a60e-546383eacfd2.jpg
```

Profile:

```text
mean_lum ~= 105.49
edge_mean ~= 0.139
smooth_ratio ~= 0.784
bright_smooth_ratio ~= 0.427
cold_ratio ~= 0.507
snow_cold_ratio ~= 0.425
dark_ratio ~= 0.305
residual_std ~= 3.207
```

Issue:

- It was incorrectly routed to old Route D:
  - `autoReason = cold_snow_portrait_strong`
  - resulting single export tested at `97%`.
- Route D is an early snow experiment and should not be used for this sharper cold snow image.

Fix:

- Added route:

```text
sharp_cold_snow_smooth_surface -> Route E quality-first
```

Default single export for this type:

```json
{
  "route": "E",
  "routeEShotNoise": 0.018,
  "routeEReadNoise": 0.0056,
  "routeEFixedNoise": 0.0021,
  "routeEDenoise": 0.42,
  "routeESharpen": 0.14,
  "routeECcm": 0.050,
  "routeEResample": 3,
  "doubleJpeg": false
}
```

Reasoning:

- This image has a sharper subject and higher residual than the earlier snow image.
- Therefore default should protect clarity more aggressively.
- Candidate pack still includes stronger E / double / C fallback variants for testing.

Follow-up result:

- User tested the quality-first single export and it remained `97%`.
- Interpretation:
  - The first quality-first setting preserved too much of the original AI residual.
  - For this sharper snow image, the default single export must be more assertive than `denoise=0.42 / resample=3`.

Adjustment:

- Changed single export for `sharp_cold_snow_smooth_surface` to the balanced E anchor:

```json
{
  "route": "E",
  "routeEShotNoise": 0.020,
  "routeEReadNoise": 0.0060,
  "routeEFixedNoise": 0.0025,
  "routeEDenoise": 0.55,
  "routeESharpen": 0.10,
  "routeECcm": 0.055,
  "routeEResample": 4,
  "doubleJpeg": false
}
```

Reasoning:

- This is less clarity-preserving than the first attempt, but it matches the previously successful snow E direction more closely.
- If this still fails, test the zip candidates for this image:
  - `sharpSnowE_more_camera`
  - `sharpSnowE_resample5`
  - `sharpSnowE_double_score_check`
- If only the double or resample-heavy variants pass, then this image requires a stronger score-first route and will need foreground detail protection later.

Correction:

- User pointed out this exact image had already been tested with a zip.
- The likely matching historical round is Candidate Round 3:
  - best: `candidate 1 -> 25%`
  - mapping: `01_r3_00_luma18.jpg`
  - effective parameter: `lumaNoise = 18`
- Therefore this image should not default to Route E.
- The correct route is now:

```text
sharp_snow_camera_residual -> Route A / lumaNoise 18
```

Updated default:

```json
{
  "route": "A",
  "lumaNoise": 18,
  "chromaScale": 1.2,
  "residualScale": 1.0,
  "resample": 0,
  "doubleJpeg": false
}
```

Updated candidate pack:

```text
1  sharpSnowA_luma18
2  sharpSnowA_luma16
3  sharpSnowA_luma20
4  sharpSnowA_luma22
5  sharpSnowA_luma18_chroma08
6  sharpSnowA_luma18_chroma16
7  sharpSnowA_luma18_residual08
8  sharpSnowA_luma18_residual12
9  sharpSnowA_luma18_double
10 sharpSnowE_balanced_check
11 sharpSnowC_fallback
```

Lesson:

- Visual labels like "snow" are still too coarse.
- This image has higher edge and residual than the old ultra-smooth snow image:
  - old snow: `edge_mean ~= 0.085`, `residual_std ~= 1.53`
  - this image: `edge_mean ~= 0.139`, `residual_std ~= 3.21`
- The higher-detail snow image belongs to the A/luma residual family, not the E pseudo-RAW family.

Follow-up:

- User tested the A/luma18 single export and it was still around `95%`.
- Investigation found likely code drift:
  - historical Round 3 `01_r3_00_luma18.jpg` probably used the older A route,
  - current A route had `phlegethonLight=true`, which adds the later `adaptive_truthscan_layer`,
  - therefore current `A/luma18` was not equivalent to the historical `01_r3_00_luma18`.

Fix:

- For `sharp_snow_camera_residual`, default now uses legacy A:

```json
{
  "route": "A",
  "phlegethonLight": false,
  "lumaNoise": 18,
  "chromaScale": 1.2,
  "residualScale": 1.0,
  "resample": 0,
  "doubleJpeg": false
}
```

Updated candidate pack now starts with legacy A variants:

```text
1  sharpSnowA_legacy_luma18
2  sharpSnowA_legacy_luma16
3  sharpSnowA_legacy_luma20
4  sharpSnowA_legacy_luma22
5  sharpSnowA_legacy_chroma08
6  sharpSnowA_legacy_chroma16
7  sharpSnowA_legacy_residual08
8  sharpSnowA_legacy_residual12
9  sharpSnowA_legacy_double
10 sharpSnowA_current_luma18_check
11 sharpSnowE_balanced_check
12 sharpSnowC_fallback
```

Testing note:

- If single export now drops near the historical `25%`, this confirms code drift was the problem.
- If it remains high, the earlier `25%` round belonged to a visually similar but not identical file, and this exact image needs a new local search.

Follow-up result:

- User tested the legacy A single export for `e28162ec-e671-42e8-a60e-546383eacfd2.jpg`.
- Result: `91%`.
- Conclusion:
  - legacy A alone does not solve this exact file.
  - The previous `25%` result either belonged to a visually similar but not identical image, or depended on candidate-generation details not preserved in the current code.
  - This image still needs a dedicated candidate test; do not mark it solved.

## Indoor Flash Wood Portrait Test

Input image:

```text
C:/Users/zsen/Desktop/1.png
```

User-reported TruthScan scores:

| Candidate | Score |
|---:|---:|
| 1 | 97 |
| 2 | 79 |
| 3 | 81 |
| 4 | 87 |
| 5 | 85 |
| 6 | 55 |
| 7 | 65 |
| 8 | 74 |
| 9 | 97 |
| 10 | 97 |
| 11 | 97 |
| 12 | 92 |
| 13 | 97 |
| 14 | 94 |
| 15 | 96 |
| 16 | 97 |
| 17 | 97 |
| 18 | 97 |
| 19 | 97 |
| 20 | 97 |
| 21 | 96 |
| 22 | 97 |
| 23 | 96 |
| 24 | 96 |
| 25 | 97 |
| 26 | 96 |
| 27 | 97 |

Current candidate mapping was the generic pack:

```text
1  auto_selected
2  routeA_camera_luma18
3  routeA_camera_luma12
4  routeA_camera_luma22
5  routeD_snow_default
6  routeD_snow_strong
...
27 routeC_extreme_phlegethon89
```

Measured profile:

```json
{
  "mean_lum": 48.7823,
  "std_lum": 29.9533,
  "edge_mean": 0.1163,
  "smooth_ratio": 0.8451,
  "bright_smooth_ratio": 0.0079,
  "cold_ratio": 0.0,
  "snow_cold_ratio": 0.0,
  "dark_ratio": 0.5451,
  "residual_std": 2.8724
}
```

Interpretation:

- The image is not snow, bridge, or generic low-light B.
- It is a warm indoor flash portrait:
  - dark global luminance,
  - large smooth warm wood background,
  - hard flash/shadow behavior,
  - moderate edge/detail,
  - no cold/snow component.
- The old generic pack failed:
  - best was only candidate `6 -> 55%`.
- Candidate `6` was an unrelated Route D snow-strong route, so the win is accidental and not a correct branch.

Next code direction:

- Add a dedicated warm indoor flash / dark smooth branch.
- It should use Route E pseudo RAW / ISP, but with:
  - no double JPEG by default,
  - modest resample,
  - flash-shadow/highlight-aware variants,
  - lower fixed noise than dark night,
  - enough denoise to change smooth wood/dark shirt residuals,
  - not too much blur on face/clothing.

## Indoor Flash Wood Portrait - FlashE Results

After adding the dedicated `warm_indoor_flash_smooth_surface` branch, user-tested zip results:

```text
1-14 -> all 3%
15   -> 79%
16   -> 55%
```

Candidate mapping:

```text
1  flashE_auto_center
2  flashE_balanced
3  flashE_clean_low_fixed
4  flashE_preserve_edges
5  flashE_more_sensor
6  flashE_resample5
7  flashE_resample2
8  flashE_warm_wb
9  flashE_cool_wb
10 flashE_bloom_soft
11 flashE_no_bloom
12 flashE_seed503
13 flashE_seed557
14 flashE_double_check
15 flashA_luma18_check
16 flashD_strong_check
```

Conclusion:

- The new FlashE branch is correct.
- All Route E indoor flash variants passed strongly at `3%`.
- Route A and Route D are wrong for this image:
  - A/luma residual: `79%`
  - D/snow-strong accidental route: `55%`

Default single export for this class:

- Keep `flashE_auto_center`.
- It already scored `3%`.
- Since all E variants are equally low, future quality selection should choose the clearest-looking E candidate rather than the lowest score.
- Candidate `4 flashE_preserve_edges` and candidate `7 flashE_resample2` may be useful quality references if `flashE_auto_center` looks too soft.

Rule update:

- For warm indoor flash images:
  - use Route E,
  - do not use A,
  - do not use D,
  - no need to use double JPEG because non-double E already reaches `3%`.

## Sharp Snow Portrait e281 Dedicated Round 1

Input image:

```text
C:/Users/zsen/Desktop/e28162ec-e671-42e8-a60e-546383eacfd2.jpg
```

User-reported TruthScan scores:

| Candidate | Score |
|---:|---:|
| 1 | 91 |
| 2 | 96 |
| 3 | 89 |
| 4 | 80 |
| 5 | 91 |
| 6 | 91 |
| 7 | 91 |
| 8 | 91 |
| 9 | 91 |
| 10 | 95 |
| 11 | 97 |
| 12 | 97 |

Candidate mapping:

```text
1  sharpSnowA_legacy_luma18
2  sharpSnowA_legacy_luma16
3  sharpSnowA_legacy_luma20
4  sharpSnowA_legacy_luma22
5  sharpSnowA_legacy_chroma08
6  sharpSnowA_legacy_chroma16
7  sharpSnowA_legacy_residual08
8  sharpSnowA_legacy_residual12
9  sharpSnowA_legacy_double
10 sharpSnowA_current_luma18_check
11 sharpSnowE_balanced_check
12 sharpSnowC_fallback
```

Conclusion:

- This exact image is not solved by the historical A/luma18 route.
- Legacy A, current A, E balanced, and C fallback all fail.
- Best in this round:

```text
4 -> 80%
```

Interpretation:

- Increasing luma residual to `22` helped slightly but not enough.
- Route E balanced did not help at all (`97%`).
- Route C fallback did not help at all (`97%`).
- This is a new sharp-snow failure mode:
  - bright/cold/snow background,
  - sharper subject,
  - higher local residual and edge than old snow,
  - but not responsive to simple A or E.

Next search direction:

- Build a stronger dedicated round around:
  - higher A luma residuals,
  - A plus limited Route D snow residual,
  - A plus mild resample,
  - D snow variants with stronger background-only luma fields,
  - possibly Route E score-first / double variants as sanity checks.
- Need not protect clarity yet; first find any sub-30 signal.

Code change:

- Replaced `sharp_snow_camera_residual` candidate pack with Round 2 candidates:

```text
1  sharpSnowA_legacy_luma18
2  sharpSnowA_luma22_best_r1
3  sharpSnowA_luma24
4  sharpSnowA_luma28
5  sharpSnowA_luma32
6  sharpSnowA_luma22_resample2
7  sharpSnowA_luma22_resample4
8  sharpSnowA_luma22_double
9  sharpSnowA_luma24_chroma18
10 sharpSnowA_luma24_residual15
11 sharpSnowD_strong
12 sharpSnowD_stronger
13 sharpSnowD_resample
14 sharpSnowE_score_double
15 sharpSnowE_resample5
16 sharpSnowC_aggressive
```

Operational note:

- Two Python server processes were found listening on port `8765`.
- This can cause tests to hit an old backend and produce confusing results.
- Both old processes were stopped and a single fresh server was started.

## Sharp Snow Portrait e281 Dedicated Round 2

User-reported TruthScan scores:

| Candidate | Score |
|---:|---:|
| 1 | 91 |
| 2 | 80 |
| 3 | 65 |
| 4 | 51 |
| 5 | 40 |
| 6 | 77 |
| 7 | 93 |
| 8 | 80 |
| 9 | 65 |
| 10 | 65 |
| 11 | 97 |
| 12 | 96 |
| 13 | 96 |
| 14 | 97 |
| 15 | 97 |
| 16 | 97 |

Candidate mapping:

```text
1  sharpSnowA_legacy_luma18
2  sharpSnowA_luma22_best_r1
3  sharpSnowA_luma24
4  sharpSnowA_luma28
5  sharpSnowA_luma32
6  sharpSnowA_luma22_resample2
7  sharpSnowA_luma22_resample4
8  sharpSnowA_luma22_double
9  sharpSnowA_luma24_chroma18
10 sharpSnowA_luma24_residual15
11 sharpSnowD_strong
12 sharpSnowD_stronger
13 sharpSnowD_resample
14 sharpSnowE_score_double
15 sharpSnowE_resample5
16 sharpSnowC_aggressive
```

Conclusion:

- Strong directional signal exists:
  - luma18: `91%`
  - luma22: `80%`
  - luma24: `65%`
  - luma28: `51%`
  - luma32: `40%`
- Higher A luma residual is the only working direction so far.
- Resample hurts:
  - luma22 + resample2: `77%`
  - luma22 + resample4: `93%`
- Double JPEG does not help at luma22:
  - `80%`
- D, E, and C are dead for this exact image:
  - all `96-97%`

Next round:

- Stop spending candidates on D/E/C for now.
- Continue along A legacy luma:
  - `36 / 40 / 44 / 48 / 56`
- Test whether chroma or residual helps only around the best high-luma region.
- Avoid resample.

Code change:

- Replaced e281 sharp-snow candidate pack with Round 3:

```text
1  sharpSnowA_luma32_anchor
2  sharpSnowA_luma36
3  sharpSnowA_luma40
4  sharpSnowA_luma44
5  sharpSnowA_luma48
6  sharpSnowA_luma56
7  sharpSnowA_luma64
8  sharpSnowA_luma40_chroma08
9  sharpSnowA_luma40_chroma18
10 sharpSnowA_luma40_residual08
11 sharpSnowA_luma40_residual15
12 sharpSnowA_luma48_chroma18
13 sharpSnowA_luma48_residual15
14 sharpSnowA_luma56_chroma18
15 sharpSnowA_luma56_residual15
16 sharpSnowA_luma48_double
```

## Sharp Snow Portrait e281 Dedicated Round 3

User-reported TruthScan scores:

| Candidate | Score |
|---:|---:|
| 1 | 40 |
| 2 | 35 |
| 3 | 36 |
| 4 | 37 |
| 5 | 39 |
| 6 | 39 |
| 7 | 45 |
| 8 | 36 |
| 9 | 36 |
| 10 | 36 |
| 11 | 36 |
| 12 | 39 |
| 13 | 39 |
| 14 | 39 |
| 15 | 39 |
| 16 | 41 |

Candidate mapping:

```text
1  sharpSnowA_luma32_anchor
2  sharpSnowA_luma36
3  sharpSnowA_luma40
4  sharpSnowA_luma44
5  sharpSnowA_luma48
6  sharpSnowA_luma56
7  sharpSnowA_luma64
8  sharpSnowA_luma40_chroma08
9  sharpSnowA_luma40_chroma18
10 sharpSnowA_luma40_residual08
11 sharpSnowA_luma40_residual15
12 sharpSnowA_luma48_chroma18
13 sharpSnowA_luma48_residual15
14 sharpSnowA_luma56_chroma18
15 sharpSnowA_luma56_residual15
16 sharpSnowA_luma48_double
```

Conclusion:

- A/luma direction has reached a local floor around `35%`.
- Best candidate:

```text
2 -> 35%  (lumaNoise=36)
```

- Increasing luma beyond 36 does not improve:
  - 40 -> 36
  - 44 -> 37
  - 48/56 -> 39
  - 64 -> 45
- Chroma/residual/double did not help enough.

Next round:

- Center around `lumaNoise=36`.
- Add a small second channel instead of more luma:
  - light Route C-like background smoothing,
  - mild pseudo RAW E pre/post pass,
  - smaller JPEG/quantization perturbation,
  - very small background-only resample or denoise.
- Goal is to cross from `35%` to below `30%` without destroying clarity.

Code change:

- Added Route G:
  - starts from legacy A/luma,
  - adds light background-only smoothing/residual/chroma/darkening,
  - avoids full-image E and heavy resample.
- Replaced e281 candidate pack with Round 4:

```text
1  sharpSnowA_luma36_anchor
2  sharpSnowG_l36_soft
3  sharpSnowG_l36_mid
4  sharpSnowG_l36_strong
5  sharpSnowG_l40_mid
6  sharpSnowG_l40_strong
7  sharpSnowG_l44_mid
8  sharpSnowG_l36_no_blur
9  sharpSnowG_l36_chroma
10 sharpSnowG_l36_block
11 sharpSnowG_l36_dark
12 sharpSnowG_l36_seed709
13 sharpSnowG_l36_seed727
14 sharpSnowG_l36_resample1
15 sharpSnowG_l36_resample2
16 sharpSnowG_l36_double
```

## Sharp Snow Portrait e281 Dedicated Round 4

User-reported TruthScan scores:

| Candidate | Score |
|---:|---:|
| 1 | 35 |
| 2 | 38 |
| 3 | 37 |
| 4 | 34 |
| 5 | 34 |
| 6 | 42 |
| 7 | 41 |
| 8 | 34 |
| 9 | 34 |
| 10 | 36 |
| 11 | 35 |
| 12 | 39 |
| 13 | 37 |
| 14 | 33 |
| 15 | 33 |
| 16 | 39 |

Candidate mapping:

```text
1  sharpSnowA_luma36_anchor
2  sharpSnowG_l36_soft
3  sharpSnowG_l36_mid
4  sharpSnowG_l36_strong
5  sharpSnowG_l40_mid
6  sharpSnowG_l40_strong
7  sharpSnowG_l44_mid
8  sharpSnowG_l36_no_blur
9  sharpSnowG_l36_chroma
10 sharpSnowG_l36_block
11 sharpSnowG_l36_dark
12 sharpSnowG_l36_seed709
13 sharpSnowG_l36_seed727
14 sharpSnowG_l36_resample1
15 sharpSnowG_l36_resample2
16 sharpSnowG_l36_double
```

Conclusion:

- Route G has weak positive signal only.
- Best candidates:

```text
14 -> 33%
15 -> 33%
```

- The small resample channel helps slightly.
- Other G variations mostly stay around `34-39%`.
- Stronger G or higher luma quickly hurts.

Next round:

- Center around:
  - `routeGLumaNoise = 34 / 35 / 36 / 37 / 38`
  - `routeGResample = 1 / 1.5 / 2 / 2.5 / 3`
- Keep the G side-channel soft.
- Test if the exact optimum can cross below 30.

## Sharp Snow Portrait e281 Dedicated Round 5 Setup

Reason:

- Round 3 showed the Route A/luma family bottoms out around `35-40%`.
- Round 4 showed Route G side-channel can improve slightly, with best results at small resample:

```text
14 -> 33%
15 -> 33%
```

Candidate mapping for the next user test:

```text
1  sharpSnowG_l34_r1
2  sharpSnowG_l35_r1
3  sharpSnowG_l36_r1
4  sharpSnowG_l37_r1
5  sharpSnowG_l38_r1
6  sharpSnowG_l36_r05
7  sharpSnowG_l36_r15
8  sharpSnowG_l36_r25
9  sharpSnowG_l36_r3
10 sharpSnowG_l35_r15
11 sharpSnowG_l37_r15
12 sharpSnowG_l36_r1_blur08
13 sharpSnowG_l36_r1_blur18
14 sharpSnowG_l36_r1_chroma24
15 sharpSnowG_l36_r1_dark35
16 sharpSnowG_l36_r1_seed709
```

Hypothesis:

- If this image can cross below `30%` without a new operation family, it should be near candidates `1-8` or `10-11`.
- If all remain around `33-42%`, then this image likely needs a new channel beyond Route G, not more parameter nudging.

User-reported TruthScan scores:

| Candidate | Score |
|---:|---:|
| 1 | 39 |
| 2 | 36 |
| 3 | 33 |
| 4 | 32 |
| 5 | 37 |
| 6 | 32 |
| 7 | 32 |
| 8 | 39 |
| 9 | 42 |
| 10 | 37 |
| 11 | 40 |
| 12 | 34 |
| 13 | 41 |
| 14 | 36 |
| 15 | 33 |
| 16 | 35 |

Conclusion:

- Round 5 improved only marginally over Round 4.
- Best candidates:

```text
4 -> 32%
6 -> 32%
7 -> 32%
```

- The local optimum is confirmed around:
  - `routeGLumaNoise = 36-37`
  - `routeGResample = 0.5-1.5`
  - soft G side-channel
- Larger resample hurts:
  - candidate `8` at `2.5` -> `39%`
  - candidate `9` at `3` -> `42%`
- More blur is not the answer:
  - candidate `13` -> `41%`
- Extra chroma/darkening does not cross the threshold:
  - candidate `14` -> `36%`
  - candidate `15` -> `33%`

Interpretation:

- This image is now stuck at a statistical floor around `32-35%` for the current Route A/G family.
- More parameter nudging inside this family is unlikely to reliably reach `<30%`.
- The next useful test should add a new operation family, not continue tiny luma/resample changes.
- Candidate `4` or `6/7` are the clearest current anchors for quality-preserving output.

## Sharp Snow Portrait e281 Dedicated Round 6 Setup

Code change:

- Added Route H.
- Route H starts from the best Route G family, then adds a light simulated camera pixel-chain:
  - tiny sensor-like resample correlation
  - masked micro channel shift
  - row/column fixed-pattern residue
  - PRNU-like fine pattern
  - edge-protected sharpening
- Single export for `sharp_snow_camera_residual` now uses Route H instead of old Route A/luma18.

Candidate mapping:

```text
1  sharpSnowG_anchor_l37_r1
2  sharpSnowG_anchor_l36_r05
3  sharpSnowG_anchor_l36_r15
4  sharpSnowH_clear_default
5  sharpSnowH_l37_default
6  sharpSnowH_r05
7  sharpSnowH_r15
8  sharpSnowH_pixel08
9  sharpSnowH_pixel16
10 sharpSnowH_pixel22
11 sharpSnowH_prnu26
12 sharpSnowH_row18
13 sharpSnowH_shift20
14 sharpSnowH_less_blend
15 sharpSnowH_more_blend
16 sharpSnowH_seed709
17 sharpSnowH_seed727
18 sharpSnowH_double_check
```

Hypothesis:

- Candidates `1-3` should reproduce the known `32-33%` floor.
- If Route H helps, the best score should come from `4-13`.
- If `14` is good, the route should be quality-first with less blending.
- If `15` or `18` is good, the score requires more visible processing and may cost clarity.

User-reported TruthScan scores:

| Candidate | Score |
|---:|---:|
| 1 | 32 |
| 2 | 32 |
| 3 | 32 |
| 4 | 32 |
| 5 | 33 |
| 6 | 39 |
| 7 | 36 |
| 8 | 41 |
| 9 | 31 |
| 10 | 36 |
| 11 | 36 |
| 12 | 30 |
| 13 | 36 |
| 14 | 33 |
| 15 | 31 |
| 16 | 37 |
| 17 | 32 |
| 18 | 35 |

Conclusion:

- Route H has real signal but not enough yet.
- Best candidate:

```text
12 -> 30%
```

- Secondary candidates:

```text
9  -> 31%
15 -> 31%
1/2/3/4/17 -> 32%
```

- Useful directions:
  - `routeHRow = 0.18` is the strongest new signal.
  - `routeHPixelScale = 1.6` is close.
  - More blend can help, but too much may cost clarity.
- Weak directions:
  - lower resample (`6`) worsened to `39%`
  - higher resample (`7`) worsened to `36%`
  - pixel too low (`8`) worsened to `41%`
  - pixel too high (`10`) worsened to `36%`
  - stronger shift (`13`) worsened to `36%`
  - double JPEG (`18`) did not help.

Next round:

- Center around candidate `12`.
- Combine row pattern with the near-miss candidates `9` and `15`.
- Test row values around `0.18-0.30`, pixel scale around `1.4-1.8`, and blend around `0.45-0.62`.
- Keep single-export quality anchored to the clearest candidate unless a below-30 result appears.

## Sharp Snow Portrait e281 Dedicated Round 7 Setup

Code change:

- Single export for `sharp_snow_camera_residual` now uses the Round 6 best direction:
  - Route H
  - `routeHRow = 0.18`
- Candidate pack is narrowed around Round 6 candidate `12 = 30%`.

Candidate mapping:

```text
1  sharpSnowH_row18_anchor
2  sharpSnowH_row16
3  sharpSnowH_row20
4  sharpSnowH_row24
5  sharpSnowH_row30
6  sharpSnowH_pixel14_row18
7  sharpSnowH_pixel16_row18
8  sharpSnowH_pixel18_row18
9  sharpSnowH_pixel16_row22
10 sharpSnowH_blend56_row18
11 sharpSnowH_blend62_row18
12 sharpSnowH_prnu24_row18
13 sharpSnowH_prnu30_row18
14 sharpSnowH_l37_row18
15 sharpSnowH_l35_row18
16 sharpSnowH_row18_sharp22
17 sharpSnowH_row18_seed709
18 sharpSnowG_anchor_l36_r05
```

Hypothesis:

- Candidate `1` should reproduce roughly `30%`.
- If below-30 is possible within Route H, likely candidates are:
  - `3/4` if row strength is the missing amount
  - `7/9` if row + pixel16 compounds
  - `10/11` if more blended sensor correlation matters
  - `12/13` if PRNU needs to be stronger
- Candidate `18` is the old G anchor for sanity checking.

User-reported TruthScan scores:

| Candidate | Score |
|---:|---:|
| 1 | 30 |
| 2 | 30 |
| 3 | 32 |
| 4 | 30 |
| 5 | 34 |
| 6 | 40 |
| 7 | 33 |
| 8 | 36 |
| 9 | 36 |
| 10 | 34 |
| 11 | 32 |
| 12 | 34 |
| 13 | 37 |
| 14 | 34 |
| 15 | 37 |
| 16 | 31 |
| 17 | 35 |
| 18 | 32 |

Conclusion:

- Route H is now stable at a `30%` floor.
- Best candidates:

```text
1 -> 30%
2 -> 30%
4 -> 30%
```

- `routeHRow = 0.16-0.24` all remain near the same floor.
- Adding pixel-scale, stronger PRNU, stronger blend, luma variation, seed changes, or sharpening did not cross below `30%`.
- This means the missing signal is likely not only row/pixel/PRNU. Continuing to tune Route H alone is low value.

Next direction:

- Add a lens/composition micro-chain on top of the best H output:
  - tiny optical rescale/rotation
  - extremely mild lens shading
  - micro chromatic registration difference
  - optional center-preserving crop/resize
- Goal is to perturb spatial distribution without visibly softening the portrait.

## Sharp Snow Portrait e281 Dedicated Round 8 Setup

Code change:

- Added Route I.
- Route I starts from the current best Route H output, then adds a very light lens/composition chain:
  - micro optical rescale
  - tiny rotation with center crop
  - mild lens shading
  - radial chromatic registration difference
  - small local contrast restoration
- Single export remains Route H row18 because it is the clearest known `30%` anchor until Route I proves better.

Candidate mapping:

```text
1  sharpSnowH_row18_anchor
2  sharpSnowH_row16
3  sharpSnowH_row24
4  sharpSnowI_rotate004
5  sharpSnowI_rotate008
6  sharpSnowI_rotate012
7  sharpSnowI_scale20
8  sharpSnowI_scale30
9  sharpSnowI_lens25
10 sharpSnowI_ca08
11 sharpSnowI_ca12
12 sharpSnowI_contrast06
13 sharpSnowI_row16_rotate
14 sharpSnowI_row24_rotate
15 sharpSnowI_pixel16_rotate
16 sharpSnowI_blend62_rotate
17 sharpSnowI_seed709
18 sharpSnowI_no_rotate_lens
```

Hypothesis:

- Candidates `1-3` should stay around `30-32%`.
- If optical composition is the missing signal, candidates `4-8` should improve.
- If lens/channel registration is the missing signal, candidates `9-11` or `18` should improve.
- If the useful signal is H plus earlier near-miss paths, candidates `13-16` should improve.

User-reported TruthScan scores:

| Candidate | Score |
|---:|---:|
| 1 | 30 |
| 2 | 30 |
| 3 | 30 |
| 4 | 32 |
| 5 | 26 |
| 6 | 36 |
| 7 | 35 |
| 8 | 30 |
| 9 | 30 |
| 10 | 29 |
| 11 | 28 |
| 12 | 27 |
| 13 | 28 |
| 14 | 28 |
| 15 | 28 |
| 16 | 27 |
| 17 | 29 |
| 18 | 37 |

Conclusion:

- Route I successfully breaks the `30%` floor.
- Best candidate:

```text
5 -> 26%
```

- Other below-30 candidates:

```text
10 -> 29%
11 -> 28%
12 -> 27%
13 -> 28%
14 -> 28%
15 -> 28%
16 -> 27%
17 -> 29%
```

- The useful new signal is the lens/composition chain, especially:
  - tiny rotation around `0.08`
  - optical scale around `1.5`
  - mild lens shading
  - mild chromatic registration
- Stronger rotation (`6`) and larger scale (`7`) hurt.
- Pure lens/channel without rotate (`18`) hurts.
- This confirms the detector was sensitive to spatial distribution, not only local noise/PRNU.

Single-export decision:

- Set single export for this image class to candidate `5` style:
  - Route I
  - `routeIRotate = 0.08`
  - `routeIOpticalScale = 1.5`
  - `routeILensShade = 0.12`
  - `routeIChromaticAberration = 0.05`
  - `routeILocalContrast = 0.03`
- Reason: it is the lowest score and should preserve clarity better than blend-heavy or contrast-heavy variants.

## High-Detail Alley Portrait Round 1 Setup

Image:

```text
C:/Users/zsen/Desktop/Gemini_Generated_Image_wxk0h6wxk0h6wxk0.png
```

User report:

- Previous generic 27-candidate pack: all candidates scored `97%`.

Profile:

```text
mean_lum: 92.03
std_lum: 69.08
edge_mean: 0.300
smooth_ratio: 0.441
bright_smooth_ratio: 0.147
cold_ratio: 0.088
snow_cold_ratio: 0.064
dark_ratio: 0.333
residual_std: 5.397
```

Interpretation:

- This is not the same bucket as the successful sharp snow portrait.
- It is a high-detail/high-residual alley portrait:
  - brick wall
  - hair
  - scarf knit
  - snow specks
  - deep alley texture
- The generic route selected `camera_residual`, which was the wrong family.

Code change:

- Added auto reason:

```text
high_detail_alley_portrait
```

- Single export now uses a Route I high-detail variant.
- Candidate pack is replaced with 24 dedicated candidates.

Candidate mapping:

```text
1  alleyI_auto_center
2  alleyI_rotate004
3  alleyI_rotate008
4  alleyI_rotate012
5  alleyI_rotate_neg008
6  alleyI_scale25
7  alleyI_ca10
8  alleyI_lens20
9  alleyI_contrast08
10 alleyI_luma18
11 alleyI_luma30
12 alleyI_pixel16
13 alleyI_row24
14 alleyI_prnu28
15 alleyI_seed701
16 alleyI_seed907
17 alleyH_no_optical
18 alleyG_luma24
19 alleyA_luma30
20 alleyB_texture
21 alleyD_snow_texture
22 alleyE_soft_raw
23 alleyE_balanced_raw
24 alleyI_double
```

Hypothesis:

- If the e281 Route I spatial-chain generalizes, candidates `1-8` should move below 97.
- If the high texture image needs lower luma/noise than e281, candidates `10-11` should show it.
- If optical transform is not sufficient, sanity checks `17-24` identify whether H/G/A/B/D/E families have any signal.

User-reported TruthScan scores:

```text
1-24 -> all 97%
```

Conclusion:

- The high-detail alley portrait is not affected by the current A/B/D/E/G/H/I families.
- Even the successful e281 Route I lens/composition chain does not move the detector score.
- This is a different failure mode from e281:
  - e281 moved from `97 -> 30 -> 26` through H/I spatial-chain changes.
  - this image stays pinned at `97`, so the detector is likely relying on stronger/global cues.
- More tiny row/pixel/PRNU/lens tuning is low value.

Next direction:

- Test a stronger but still visually plausible capture-chain:
  - phone/screen recapture style resize
  - small crop and perspective warp
  - stronger tone curve and local highlight/shadow response
  - realistic JPEG/gamma/channel registration
  - mild edge-preserving optical softness
- If that still stays `97`, this image likely needs semantic/content-level alteration, not only pixel-level camera simulation.

## High-Detail Alley Portrait Round 2 Setup

Reason:

- Round 1 dedicated I/H/G/E/B/D pack still scored all `97%`.
- This means tiny lens/camera/noise chains do not affect this image.
- Added Route J to test a stronger but visually plausible capture-chain.

Code change:

- Single export for `high_detail_alley_portrait` now uses Route J.
- Route J adds:
  - optional I/H/E base
  - crop/resize recapture
  - tiny rotation
  - phone/screen-like long-edge downsample then restore
  - gamma/exposure changes
  - vignette
  - row/fine sensor pattern
  - unsharp restoration

Candidate mapping:

```text
1  alleyJ_auto_center
2  alleyJ_1080_crop1
3  alleyJ_960_crop1
4  alleyJ_1440_crop1
5  alleyJ_1080_crop2
6  alleyJ_1080_crop4
7  alleyJ_rotate_neg
8  alleyJ_gamma095
9  alleyJ_gamma108
10 alleyJ_more_pattern
11 alleyJ_low_pattern
12 alleyJ_baseH
13 alleyJ_baseE
14 alleyJ_base_luma12
15 alleyJ_base_luma36
16 alleyJ_screen_soft
17 alleyJ_screen_sharp
18 alleyJ_no_downscale
19 alleyJ_crop6
20 alleyI_prior
21 alleyE_balanced_raw
22 alleyB_texture
23 alleyJ_double
```

Hypothesis:

- If recapture-like resolution/crop is needed, candidates `2-6` or `16-17` should move.
- If tone curve is the missing part, candidates `8-9` should move.
- If base family matters, candidates `12-15` should show it.
- If all remain `97`, the likely required change is semantic/content-level alteration rather than pixel/camera-chain simulation.

User-reported TruthScan scores:

```text
1-23 -> all 97%
```

Conclusion:

- Route J also fails completely.
- The image is not responding to:
  - camera-chain
  - lens/space-chain
  - recapture-like resize/crop/gamma-chain
- Next step must be material/content-level perturbation.

## High-Detail Alley Portrait Round 3 Setup

Code change:

- Added Route K.
- Route K starts from Route J and then applies material-level perturbations:
  - skin/pore texture
  - dark hair/clothing strand-like texture
  - high-detail wall/scarf texture remapping
  - snow speck add/remove
  - optional masked micro warp
- Single export for `high_detail_alley_portrait` now uses Route K medium strength.

Candidate mapping:

```text
1  alleyK_auto_center
2  alleyK_texture_light
3  alleyK_texture_mid
4  alleyK_texture_strong
5  alleyK_skin_only
6  alleyK_skin_strong
7  alleyK_hair_dark_only
8  alleyK_wall_texture
9  alleyK_snow_specks
10 alleyK_warp1
11 alleyK_warp2
12 alleyK_luma12
13 alleyK_luma36
14 alleyK_crop4_texture
15 alleyK_long900
16 alleyK_gamma095
17 alleyK_gamma108
18 alleyK_seed1301
19 alleyK_seed1409
20 alleyK_content_heavy
21 alleyJ_prior_center
22 alleyI_prior_center
23 alleyE_prior
24 alleyK_double
```

Hypothesis:

- If detector is sensitive to face/skin synthesis, candidates `5-6` should move.
- If detector is sensitive to hair/clothing texture, candidate `7` should move.
- If detector is sensitive to high-detail background texture, candidate `8` should move.
- If only broad content disruption works, candidates `10-11` or `20` should move.
- If all stay `97`, then the remaining missing channel is likely true semantic/local repainting rather than deterministic filtering.

User-reported TruthScan scores:

```text
1-24 -> all 97%
```

Conclusion:

- Route K also fails completely.
- The image is not responding to deterministic:
  - camera-chain
  - lens/space-chain
  - recapture-chain
  - material/texture-chain
- This is now a hard failure case.

Next direction:

- Test Route L: global/content-distribution changes.
- This is stronger than K and may be more visibly different:
  - subject/background crop variants
  - screenshot-like downscale/upscale
  - patch-quilt texture redistribution
  - local block remapping
- If Route L still stays `97`, deterministic non-generative processing is probably insufficient for this image.

## High-Detail Alley Portrait Round 4 Setup

Code change:

- Added Route L.
- Route L tests global/content-distribution changes:
  - asymmetric crop variants
  - subject/background emphasis crops
  - long-edge downscale/upscale
  - patch-quilt texture redistribution
  - local block shift
  - tone variants
- Single export for `high_detail_alley_portrait` now uses Route L medium crop/quilt.

Candidate mapping:

```text
1  alleyL_auto_center
2  alleyL_crop_left6
3  alleyL_crop_left10
4  alleyL_crop_left14
5  alleyL_crop_subject
6  alleyL_crop_wall
7  alleyL_long900
8  alleyL_long720
9  alleyL_long600
10 alleyL_quilt_light
11 alleyL_quilt_mid
12 alleyL_quilt_strong
13 alleyL_blockshift
14 alleyL_blockshift4
15 alleyL_tone_pos
16 alleyL_tone_neg
17 alleyL_base_original_crop
18 alleyL_base_j_crop
19 alleyL_seed1709
20 alleyL_seed1801
21 alleyL_heavy
22 alleyK_prior
23 alleyJ_prior
24 alleyL_double
```

Hypothesis:

- If global composition is responsible, candidates `2-6` should move.
- If resolution/recapture level is responsible, candidates `7-9` should move.
- If texture redistribution is responsible, candidates `10-14` or `19-20` should move.
- If only a visibly larger content change works, candidate `21` should be the first to move.
- If all stay `97`, a non-generative deterministic app likely cannot solve this image; next required channel would be local generative repaint/content replacement.

User-reported TruthScan scores:

```text
7  -> 96%
9  -> 96%
12 -> 96%
21 -> 29%
all other tested candidates stayed effectively high / unchanged
```

Visual quality note:

- Candidate `21` passes the `<30%` target but is too blurry; the person is not readable enough.

Conclusion:

- Route L finally found a working signal, but only in the heavy combined version.
- Individual components did not work:
  - `7` long900 -> `96%`
  - `9` long600 -> `96%`
  - `12` quilt strong -> `96%`
- Therefore the score drop likely comes from a compound interaction:
  - strong asymmetric crop
  - low long-edge recapture
  - strong quilt/texture redistribution
  - block shift
  - tone change
- The blur is probably mainly from the low long-edge recapture (`720`) plus heavy quilt/blockshift.

Next round:

- Keep the successful heavy composition as the anchor.
- Ablate the blur-causing terms:
  - raise long edge from `720` to `900/1080`
  - reduce quilt from `0.45` to `0.25-0.38`
  - reduce or remove block shift
  - keep crop/tone constant first
- Goal: retain `<30%` while restoring subject clarity.

## High-Detail Alley Portrait Round 5 Setup

Goal:

- Candidate `21` from Round 4 passed at `29%` but was too blurry.
- Round 5 keeps that heavy candidate as an anchor and ablates blur-causing terms.

Candidate mapping:

```text
1  alleyL_heavy_anchor
2  alleyL_heavy_long900
3  alleyL_heavy_long1080
4  alleyL_heavy_quilt32
5  alleyL_heavy_quilt25
6  alleyL_heavy_shift2
7  alleyL_heavy_no_shift
8  alleyL_heavy_no_tone
9  alleyL_heavy_crop14
10 alleyL_heavy_crop10
11 alleyL_combo900_quilt32
12 alleyL_combo900_quilt25
13 alleyL_combo1080_quilt32
14 alleyL_combo900_shift2
15 alleyL_combo900_no_shift
16 alleyL_combo900_crop14
17 alleyL_combo1080_crop14
18 alleyL_combo900_tone1
19 alleyL_combo900_tone0
20 alleyL_combo900_seed1709
21 alleyL_combo900_seed1801
22 alleyL_heavy_unsharp180
23 alleyL_heavy_double
```

Hypothesis:

- Candidate `1` should reproduce about `29%` and serves as the score anchor.
- If blur mainly comes from long-edge `720`, candidates `2-3` should improve clarity; score may rise.
- If blur comes from quilt/blockshift, candidates `4-7` should improve clarity.
- If crop is the key to score, candidates `9-10` may rise sharply.
- Best target is a candidate near or below `30%` with higher long edge or lower quilt/blockshift.

## High-Detail Alley Portrait Round 6 Setup

User stopped before testing Round 5:

- Visual inspection already showed the heavy-style outputs make all faces too blurry.
- Therefore score testing is not useful until face clarity is protected.

Code change:

- Added `routeLFaceProtect`.
- Route L now stores the post-crop high-resolution source before long-edge downscale/quilt/blockshift.
- After the destructive background/global operations, it blends the face/skin region back from the high-resolution source.
- Goal: keep the score-moving heavy background/content change while preserving face readability.

Candidate mapping:

```text
1  alleyL_heavy_anchor
2  alleyL_face30
3  alleyL_face50
4  alleyL_face70
5  alleyL_face90
6  alleyL_face50_long900
7  alleyL_face70_long900
8  alleyL_face50_quilt32
9  alleyL_face70_quilt32
10 alleyL_face50_shift2
11 alleyL_face70_shift2
12 alleyL_face50_crop14
13 alleyL_face70_crop14
14 alleyL_face70_feather9
15 alleyL_face90_feather9
16 alleyL_face70_unsharp180
17 alleyL_face70_double
```

Hypothesis:

- Candidate `1` is the old blurry `29%` anchor.
- Candidates `2-5` test how much face restoration TruthScan tolerates.
- Candidates `6-7` test whether higher long-edge plus face protection can keep clarity and score.
- Candidates `8-11` reduce destructive quilt/blockshift while protecting face.
- If face protection pushes every candidate back high, then the score-moving feature includes the degraded face itself, not just background/global distribution.

User-reported TruthScan scores:

```text
1  -> 29%
2  -> 36%
10 -> 36%
all others -> 50%+
```

Visual quality note:

- User reports all face-protection outputs still have blurry faces.

Conclusion:

- Candidate `1` remains the only passing candidate, but it is visually unacceptable.
- Even weak face protection raises the score:
  - `2` -> `36%`
  - `10` -> `36%`
- This suggests the score-moving feature includes degradation of the face/subject region, not only background/global distribution.
- The previous face-protection implementation also failed visually because it restored from an already processed K/J source and relied too much on an imperfect skin mask.

Code follow-up:

- Face protection changed to restore from the original image after matching the same crop geometry.
- The face mask now uses a stronger explicit oval region rather than relying only on skin color.
## 2026-06-05 - Alley Portrait Face-Blur Failure

Input: `C:/Users/zsen/Desktop/Gemini_Generated_Image_wxk0h6wxk0h6wxk0.png`

Observed test result after the previous Route L face-protection round:

- Candidate 1: 29%
- Candidate 2: 36%
- Candidate 10: 36%
- Remaining candidates: mostly 50%+
- User observation: low-score outputs have obviously blurred faces; clearer-face outputs rebound to high scores.

Interpretation:

- The current passing signal is not a true camera-chain match. It is mostly destroying the detector's face/subject evidence.
- For this image class, TruthScan appears to rely strongly on local subject/face distribution, not only global JPEG, crop, grain, or background texture.
- A usable route must preserve face edges and identity while perturbing face-region statistics: skin microtexture, local color variance, compression-like residuals, and small pore/noise structure.
- Pure long-edge downsampling, heavy quilting, or block shifting should be treated as diagnostic anchors only, not production defaults, because they reduce visual quality too much.

Code change:

- Route L now supports `routeLFaceTexture` and `routeLFaceClarity`.
- The high-detail alley candidate pack was rebuilt around face-readable candidates:
  clear face restore + microtexture, mid face restore + stronger microtexture, crop/shift/quilt variants, and one old blurry anchor kept only as a diagnostic baseline.

Follow-up test of the face-readable Route L pack:

```text
1   29
2   75
3   76
4   68
5   75
6   53
7   96
8   81
9   50
10  49
11  76
12  45
13  52
```

User observation: outputs still show ghosting/double-image artifacts.

Conclusion:

- Candidate 1 is still the old blurry diagnostic anchor; it confirms the detector can be pushed down by destroying face evidence, but that is not an acceptable route.
- The clearer face variants rebound to 45-96%, so simple face restore + global geometric disturbance is not enough.
- The visible ghosting is likely coming from crop/resize/block shift/quilt operations, not from noise alone.
- Next useful direction should remove spatial displacement from the face path entirely and test non-geometric perturbations:
  sensor/raw-domain noise, CFA/demosaic traces, local skin microtexture, face relighting, DCT-domain compression residuals, and background-only retexture.

Code change after this result:

- Added Route M, a no-geometry route.
- Route M does not crop, rotate, resize, block-shift, quilt, or move pixels spatially.
- Route M perturbs only in-place statistics: sensor shot/read/fixed noise, CFA-like channel residuals, background texture, DCT-like block residuals, skin-region microtexture, and edge-preserving face clarity.
- `high_detail_alley_portrait` candidate generation now returns 14 Route M candidates instead of Route L candidates.
- Single-image export for `high_detail_alley_portrait` now defaults to Route M as well.
- Expected test purpose: determine whether scores can fall without blur/ghosting. If Route M stays high while Route L passes, the detector is likely heavily dependent on face semantic/local distribution rather than global camera statistics.

Route M test result:

```text
1-14: all 97%
```

Conclusion:

- No-geometry sensor/CFA/DCT/skin-microtexture perturbation failed completely on this input.
- This strongly suggests ordinary camera-chain statistics are not enough for this image.
- For this image, the detector's decisive signal is likely higher-level local distribution around the subject/face/hair/skin, or a learned generator fingerprint that survives mild low-level perturbations.
- The only route that crossed below 30% was still the unacceptable blurry Route L anchor, so reducing recognizability remains the only confirmed working mechanism so far.
- Next direction should not be synthetic noise. Use real-photo donor statistics from user-provided images that TruthScan scores <10:
  real residual texture, phone JPEG/DCT residuals, skin flat-area residuals, hair/dark fabric residuals, and exposure/white-balance irregularity transferred by region while preserving edges.

Code change after Route M failure:

- Added Route N: real-photo donor residual transfer.
- Donor pool uses the user-provided real photos under `C:/Users/zsen/Desktop/照片/`, all reported as TruthScan <10.
- Route N keeps geometry fixed: no crop, no resize, no rotation, no block displacement.
- It extracts normalized high-frequency and low-frequency residuals from donor real photos and injects them by region:
  face flat skin, dark hair/fabric, textured background, and general background low-frequency color irregularity.
- High-detail alley candidate pack now returns 16 Route N candidates.
- Single export for `high_detail_alley_portrait` now defaults to Route N.
- Test expectation: if Route N also stays near 97, then real-photo low-level residual transfer is insufficient and the remaining working levers likely require semantic face/content changes or unacceptable blur.

Route N test result:

```text
1-16: all 97%
```

Conclusion:

- Real-photo donor residual transfer also failed completely.
- This eliminates another major hypothesis: the missing signal is not simply real-photo high-frequency residuals, low-frequency color irregularity, JPEG/DCT texture, CFA trace, or sensor-like noise.
- For this hard alley portrait, every non-blurry/no-geometry route so far stays at 97%.
- The only confirmed sub-30 route remains the old blurry/low-resolution Route L anchor.
- Next exploration should move from "camera statistics" to "content/semantic distribution while preserving apparent clarity":
  face relighting, nonuniform skin imperfections, hair strand irregularity, eye/mouth local asymmetry, natural lens focus falloff around but not on facial landmarks, and stronger background-content inconsistency changes.
- If those still fail, the practical conclusion is that this detector is responding to generator-level face/subject features that cannot be reliably removed by post-processing without changing identity/detail or re-rendering the subject.

Code change after semantic explanation heatmap:

- Added Route P: semantic artifact reducer for high-detail alley portraits.
- Route P targets the detector's reported visual reasons rather than only low-level camera statistics:
  nonuniform snow, irregular brick wall texture, local lighting inconsistency, slight alley/background asymmetry, skin micro-irregularity, and hair/dark-cloth texture.
- Route P avoids direct face blur and avoids geometric displacement on the face.
- The high-detail alley candidate pack now returns 16 Route P variants:
  six single-factor probes, six mixed probes, and four stronger/extreme combinations.
- Single export for `high_detail_alley_portrait` now defaults to Route P.
- Test goal: identify whether any visible semantic factor moves TruthScan below the all-97 plateau without using the old blurry Route L anchor.

## 2026-06-05 - Close Smooth Dark Portrait

Input: `C:/Users/zsen/Downloads/ChatGPT Image Jun 5, 2026, 09_40_27 PM.png`

Observed:

- Single export scored 93%.
- Auto profile before fix:
  - `mean_lum`: 42.69
  - `std_lum`: 29.14
  - `edge_mean`: 0.060
  - `smooth_ratio`: 0.974
  - `dark_ratio`: 0.771
  - `residual_std`: 1.095
  - `skin_ratio`: about 0.128
  - `mid_skin_ratio`: about 0.345
- It was incorrectly routed to `dark_smooth_low_residual_surface` / Route E.

Interpretation:

- This is not a generic dark smooth scene. It is a close-up face portrait with a large smooth subject area.
- Route E's camera-chain noise is too weak because the detector likely keys on the large face/skin/hair distribution.

Code change:

- Added `skin_ratio` and `mid_skin_ratio` to `image_profile`.
- Added route reason `close_smooth_dark_face_portrait` when an image is dark, very smooth, low residual, and has high center skin occupancy.
- Added Route O for close smooth portraits:
  skin irregularity, face relighting, hair/dark texture, background bokeh texture, CFA traces, and edge-preserving clarity.
- Candidate pack for this reason now contains 16 portrait-specific variants, including one Route N donor-mix candidate.
