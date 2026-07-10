from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path
from PIL import Image
import csv
import itertools
import io
import json
import os
import time

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

BASE = {
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

GRID = {
    "truthscanStrength": [0, 0.2, 0.4, 0.7, 1.0],
    "residualScale": [0, 0.25, 0.5, 0.8, 1.0],
    "chromaScale": [0, 0.4, 0.8, 1.2],
    "grain": [0, 1, 2, 3, 4],
    "edgeNoise": [0, 1, 3, 5],
    "lumaNoise": [0, 1, 3, 5],
    "chromaBlur": [1, 2, 3],
}

_worker_pairs = None


def init_worker():
    global _worker_pairs
    loaded = []
    for name, src_path, target_path in PAIRS:
        src = Image.open(src_path).convert("RGB")
        target = Image.open(target_path).convert("RGB")
        loaded.append(
            {
                "name": name,
                "src_img": src,
                "src_arr": np.asarray(src).astype(np.int16),
                "target_arr": np.asarray(target).astype(np.int16),
                "target_bytes": target_path.stat().st_size,
            }
        )
    _worker_pairs = loaded


def all_settings():
    keys = list(GRID)
    for values in itertools.product(*(GRID[key] for key in keys)):
        settings = dict(BASE)
        settings.update(dict(zip(keys, values)))
        if settings["truthscanStrength"] == 0:
            settings["residualScale"] = 0
            settings["chromaScale"] = 0
        yield settings


def evaluate(settings):
    rows = []
    total = 0.0
    for item in _worker_pairs:
        output = server.process(item["src_img"], settings)
        data = server.save_jpeg_bytes(output, settings)
        out = Image.open(io.BytesIO(data)).convert("RGB")
        out_arr = np.asarray(out).astype(np.int16)

        src_arr = item["src_arr"]
        target_arr = item["target_arr"]
        target_delta = target_arr - src_arr
        out_delta = out_arr - src_arr
        err = out_arr - target_arr

        abs_err = float(np.abs(err).mean())
        mean_err = float(np.abs(err.mean(axis=(0, 1))).mean())
        byte_err = abs(len(data) - item["target_bytes"]) / item["target_bytes"] * 8
        gt_target = float((np.abs(target_delta).max(axis=2) > 10).mean())
        gt_out = float((np.abs(out_delta).max(axis=2) > 10).mean())
        gt_err = abs(gt_out - gt_target) * 20
        score = abs_err + mean_err * 0.8 + byte_err + gt_err
        total += score
        rows.append(
            {
                "pair": item["name"],
                "score": score,
                "abs_err": abs_err,
                "mean_err": mean_err,
                "bytes": len(data),
                "target_bytes": item["target_bytes"],
                "gt10": gt_out,
                "target_gt10": gt_target,
            }
        )
    return {"total": total, "settings": settings, "rows": rows}


def main():
    out_dir = Path("analysis_outputs")
    out_dir.mkdir(exist_ok=True)
    csv_path = out_dir / "full_fit_results.csv"
    top_path = out_dir / "full_fit_top20.json"

    settings_list = list(all_settings())
    total_jobs = len(settings_list)
    print("jobs", total_jobs, "workers", max(1, (os.cpu_count() or 4) - 1), flush=True)
    start = time.time()
    top = []

    fieldnames = [
        "total",
        "settings",
        "snow_score",
        "snow_abs_err",
        "snow_mean_err",
        "snow_bytes",
        "snow_gt10",
        "bridge_score",
        "bridge_abs_err",
        "bridge_mean_err",
        "bridge_bytes",
        "bridge_gt10",
    ]
    with csv_path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        with ProcessPoolExecutor(max_workers=max(1, (os.cpu_count() or 4) - 1), initializer=init_worker) as pool:
            futures = [pool.submit(evaluate, settings) for settings in settings_list]
            for i, future in enumerate(as_completed(futures), start=1):
                result = future.result()
                row_by_pair = {row["pair"]: row for row in result["rows"]}
                csv_row = {
                    "total": result["total"],
                    "settings": json.dumps(result["settings"], sort_keys=True),
                    "snow_score": row_by_pair["snow_16"]["score"],
                    "snow_abs_err": row_by_pair["snow_16"]["abs_err"],
                    "snow_mean_err": row_by_pair["snow_16"]["mean_err"],
                    "snow_bytes": row_by_pair["snow_16"]["bytes"],
                    "snow_gt10": row_by_pair["snow_16"]["gt10"],
                    "bridge_score": row_by_pair["bridge_30"]["score"],
                    "bridge_abs_err": row_by_pair["bridge_30"]["abs_err"],
                    "bridge_mean_err": row_by_pair["bridge_30"]["mean_err"],
                    "bridge_bytes": row_by_pair["bridge_30"]["bytes"],
                    "bridge_gt10": row_by_pair["bridge_30"]["gt10"],
                }
                writer.writerow(csv_row)

                top.append(result)
                top.sort(key=lambda x: x["total"])
                top = top[:20]
                if i % 100 == 0 or i == total_jobs:
                    f.flush()
                    top_path.write_text(json.dumps(top, ensure_ascii=False, indent=2), encoding="utf-8")
                    elapsed = time.time() - start
                    print(f"{i}/{total_jobs} elapsed={elapsed:.1f}s best={top[0]['total']:.4f}", flush=True)

    top_path.write_text(json.dumps(top, ensure_ascii=False, indent=2), encoding="utf-8")
    print("done", top_path, csv_path, flush=True)
    print(json.dumps(top[:5], ensure_ascii=False, indent=2), flush=True)


if __name__ == "__main__":
    main()

