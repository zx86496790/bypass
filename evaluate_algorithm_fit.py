from pathlib import Path
from PIL import Image
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


BASE_SETTINGS = {
    "calibrated": True,
    "phlegethonLight": True,
    "brightness": -5,
    "contrast": 0.97,
    "blueShift": -1,
    "chromaBlur": 1,
    "grain": 0,
    "edgeNoise": 0,
    "resample": 0,
    "lumaNoise": 0,
    "learnedResidual": 0,
    "jpegQuality": 0.90,
    "doubleJpeg": False,
    "writeExif": False,
    "truthscanStrength": 1.0,
    "residualScale": 1.0,
    "chromaScale": 1.2,
}


def stats(name, src_path, target_path, settings):
    src = Image.open(src_path).convert("RGB")
    target = Image.open(target_path).convert("RGB")
    out = server.process(src, settings)
    data = server.save_jpeg_bytes(out, settings)
    out = Image.open(__import__("io").BytesIO(data)).convert("RGB")
    out_path = Path("analysis_outputs") / f"algorithm_{name}.jpg"
    out_path.write_bytes(data)

    src_a = np.asarray(src).astype(int)
    target_a = np.asarray(target).astype(int)
    out_a = np.asarray(out).astype(int)
    target_delta = target_a - src_a
    out_delta = out_a - src_a
    err = out_a - target_a
    print("\n", name)
    print(" target bytes", target_path.stat().st_size, "algorithm bytes", len(data), out_path)
    print(" target mean", target_delta.mean(axis=(0, 1)).round(3).tolist(),
          "abs", np.abs(target_delta).mean(axis=(0, 1)).round(3).tolist(),
          "gt10", round(float((np.abs(target_delta).max(axis=2) > 10).mean()), 4))
    print(" algo   mean", out_delta.mean(axis=(0, 1)).round(3).tolist(),
          "abs", np.abs(out_delta).mean(axis=(0, 1)).round(3).tolist(),
          "gt10", round(float((np.abs(out_delta).max(axis=2) > 10).mean()), 4))
    print(" err    mean", err.mean(axis=(0, 1)).round(3).tolist(),
          "abs", np.abs(err).mean(axis=(0, 1)).round(3).tolist(),
          "within10", round(float((np.abs(err).max(axis=2) <= 10).mean()), 4))


for pair in PAIRS:
    print(pair[0], pair[1].exists(), pair[2].exists())
    stats(*pair, BASE_SETTINGS)
