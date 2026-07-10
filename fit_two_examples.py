from pathlib import Path
from PIL import Image
import itertools
import io
import numpy as np

import server


PAIRS = [
    (
        "snow_16",
        Path(r"C:/Users/zsen/Desktop/ig_059018b641d22072016a1e5314bee0819a9a837b923e86a889.png"),
        Path("analysis_outputs/exact_passthrough_test.jpg"),
    ),
    (
        "bridge_30",
        Path(r"C:/Users/zsen/Desktop/14d2ecbf-6236-4756-8ae9-28515853b1c8.png"),
        Path("analysis_outputs/exact_bridge_passthrough_test.jpg"),
    ),
]


def evaluate(settings):
    total = 0
    rows = []
    for name, src_path, target_path in PAIRS:
        src = Image.open(src_path).convert("RGB")
        target = Image.open(target_path).convert("RGB")
        output = server.process(src, settings)
        data = server.save_jpeg_bytes(output, settings)
        out = Image.open(io.BytesIO(data)).convert("RGB")

        src_a = np.asarray(src).astype(int)
        target_a = np.asarray(target).astype(int)
        out_a = np.asarray(out).astype(int)
        err = out_a - target_a
        mean_err = np.abs(err.mean(axis=(0, 1))).mean()
        abs_err = np.abs(err).mean()
        byte_err = abs(len(data) - target_path.stat().st_size) / target_path.stat().st_size * 8
        gt_target = (np.abs(target_a - src_a).max(axis=2) > 10).mean()
        gt_out = (np.abs(out_a - src_a).max(axis=2) > 10).mean()
        gt_err = abs(gt_out - gt_target) * 20
        score = abs_err + mean_err * 0.8 + byte_err + gt_err
        total += score
        rows.append((name, score, abs_err, mean_err, len(data), target_path.stat().st_size, gt_out, gt_target))
    return total, rows


base = {
    "calibrated": True,
    "phlegethonLight": True,
    "brightness": -5,
    "contrast": 0.97,
    "blueShift": -1,
    "chromaBlur": 2,
    "grain": 0,
    "edgeNoise": 0,
    "resample": 0,
    "lumaNoise": 0,
    "learnedResidual": 0,
    "jpegQuality": 0.90,
    "doubleJpeg": False,
    "writeExif": False,
}

grid = {
    "truthscanStrength": [0, 0.2, 0.4, 0.7, 1.0],
    "residualScale": [0, 0.25, 0.5, 0.8, 1.0],
    "chromaScale": [0, 0.4, 0.8, 1.2],
    "grain": [0, 1, 2, 3, 4],
    "edgeNoise": [0, 1, 3, 5],
    "lumaNoise": [0, 1, 3, 5],
    "chromaBlur": [1, 2, 3],
}

best = []
keys = list(grid)
for values in itertools.product(*(grid[k] for k in keys)):
    settings = dict(base)
    settings.update(dict(zip(keys, values)))
    if settings["truthscanStrength"] == 0:
        settings["residualScale"] = 0
        settings["chromaScale"] = 0
    score, rows = evaluate(settings)
    best.append((score, settings, rows))
    best.sort(key=lambda x: x[0])
    best = best[:10]

for rank, (score, settings, rows) in enumerate(best, start=1):
    print("\nRANK", rank, "score", round(score, 4))
    print(settings)
    for row in rows:
        print(" ", row)

