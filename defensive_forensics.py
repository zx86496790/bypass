from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
from PIL import ExifTags, Image, ImageStat


KNOWN_PHLEGETHON_QTABLES = {
    "luma_sum": 592,
    "chroma_sum": 891,
    "luma_first8": [3, 2, 2, 3, 4, 6, 8, 10],
    "chroma_first8": [3, 3, 4, 8, 16, 16, 16, 16],
}


def gray(arr: np.ndarray) -> np.ndarray:
    arr = arr.astype(np.float32)
    return arr[..., 0] * 0.299 + arr[..., 1] * 0.587 + arr[..., 2] * 0.114


def residual_std(g: np.ndarray) -> float:
    if g.shape[0] < 3 or g.shape[1] < 3:
        return 0.0
    center = g[1:-1, 1:-1]
    nb = (g[:-2, 1:-1] + g[2:, 1:-1] + g[1:-1, :-2] + g[1:-1, 2:]) / 4
    return float((center - nb).std())


def laplacian_std(g: np.ndarray) -> float:
    if g.shape[0] < 3 or g.shape[1] < 3:
        return 0.0
    center = g[1:-1, 1:-1]
    lap = 4 * center - g[:-2, 1:-1] - g[2:, 1:-1] - g[1:-1, :-2] - g[1:-1, 2:]
    return float(lap.std())


def blockiness(g: np.ndarray) -> float:
    if g.shape[0] <= 8 or g.shape[1] <= 8:
        return 0.0
    vx = g[:, 8::8]
    vy = g[:, 7::8]
    hx = g[8::8, :]
    hy = g[7::8, :]
    v = np.abs(vx[:, : vy.shape[1]] - vy[:, : vx.shape[1]]).mean()
    h = np.abs(hx[: hy.shape[0], :] - hy[: hx.shape[0], :]).mean()
    return float((v + h) / 2)


def image_meta(path: Path) -> dict:
    image = Image.open(path)
    rgb = image.convert("RGB")
    stat = ImageStat.Stat(rgb)
    meta = {
        "path": str(path),
        "format": image.format,
        "mode": image.mode,
        "size": image.size,
        "bytes": path.stat().st_size,
        "info": {k: (f"<{len(v)} bytes>" if isinstance(v, bytes) else v) for k, v in image.info.items()},
        "exif_count": len(image.getexif()),
        "mean_rgb": [round(float(v), 4) for v in stat.mean],
        "std_rgb": [round(float(v), 4) for v in stat.stddev],
    }
    if image.format == "JPEG":
        qtables = {}
        for key, values in image.quantization.items():
            qtables[str(key)] = {
                "sum": int(sum(values)),
                "first8": [int(v) for v in values[:8]],
            }
        meta["jpeg"] = {
            "layers": getattr(image, "layers", None),
            "layer": getattr(image, "layer", None),
            "qtables": qtables,
        }
    exif = image.getexif()
    selected_exif = {}
    for tag in [271, 272, 305, 306, 282, 283, 33434, 33437, 34855, 37386, 40961]:
        value = exif.get(tag)
        if value is not None:
            selected_exif[ExifTags.TAGS.get(tag, str(tag))] = repr(value)
    if selected_exif:
        meta["selected_exif"] = selected_exif
    return meta


def fit_channels(source: np.ndarray, suspect: np.ndarray) -> list[dict]:
    rows = []
    src = source.reshape(-1, 3).astype(np.float32)
    sus = suspect.reshape(-1, 3).astype(np.float32)
    for idx, name in enumerate(["R", "G", "B"]):
        x = src[:, idx]
        y = sus[:, idx]
        design = np.vstack([x, np.ones_like(x)]).T
        gain, offset = np.linalg.lstsq(design, y, rcond=None)[0]
        corr = np.corrcoef(x, y)[0, 1]
        rows.append(
            {
                "channel": name,
                "gain": round(float(gain), 6),
                "offset": round(float(offset), 6),
                "correlation": round(float(corr), 6),
            }
        )
    return rows


def region_boxes(width: int, height: int) -> dict[str, tuple[int, int, int, int]]:
    return {
        "upper_subject": (round(width * 0.20), round(height * 0.12), round(width * 0.78), round(height * 0.52)),
        "face_center": (round(width * 0.42), round(height * 0.28), round(width * 0.72), round(height * 0.52)),
        "bright_window": (round(width * 0.48), round(height * 0.08), width, round(height * 0.70)),
        "dark_clothing": (round(width * 0.18), round(height * 0.52), round(width * 0.86), round(height * 0.95)),
        "left_wall": (0, 0, round(width * 0.30), round(height * 0.48)),
    }


def compare_regions(source: np.ndarray, suspect: np.ndarray) -> dict:
    h, w = source.shape[:2]
    rows = {}
    for name, (x0, y0, x1, y1) in region_boxes(w, h).items():
        src = source[y0:y1, x0:x1]
        sus = suspect[y0:y1, x0:x1]
        diff = sus - src
        src_g = gray(src)
        sus_g = gray(sus)
        rows[name] = {
            "box": [x0, y0, x1, y1],
            "mean_diff_rgb": [round(float(v), 4) for v in diff.mean(axis=(0, 1))],
            "mean_abs_rgb": [round(float(v), 4) for v in np.abs(diff).mean(axis=(0, 1))],
            "residual_std_source": round(residual_std(src_g), 4),
            "residual_std_suspect": round(residual_std(sus_g), 4),
            "laplacian_std_source": round(laplacian_std(src_g), 4),
            "laplacian_std_suspect": round(laplacian_std(sus_g), 4),
        }
    return rows


def jpeg_rule_hits(meta: dict) -> list[str]:
    hits = []
    jpeg = meta.get("jpeg")
    if not jpeg:
        return hits
    qtables = jpeg.get("qtables", {})
    q0 = qtables.get("0", {})
    q1 = qtables.get("1", {})
    if q0.get("sum") == KNOWN_PHLEGETHON_QTABLES["luma_sum"] and q1.get("sum") == KNOWN_PHLEGETHON_QTABLES["chroma_sum"]:
        hits.append("known_phlegethon_quant_table_sums")
    if q0.get("first8") == KNOWN_PHLEGETHON_QTABLES["luma_first8"]:
        hits.append("known_phlegethon_luma_first8")
    if q1.get("first8") == KNOWN_PHLEGETHON_QTABLES["chroma_first8"]:
        hits.append("known_phlegethon_chroma_first8")
    if meta.get("exif_count") == 0 and meta.get("info", {}).get("jfif") is not None:
        hits.append("jfif_without_exif")
    return hits


def save_heatmaps(source: np.ndarray, suspect: np.ndarray, out_dir: Path) -> dict[str, str]:
    out_dir.mkdir(parents=True, exist_ok=True)
    diff = suspect - source
    abs_diff = np.clip(np.abs(diff) * 8, 0, 255).astype(np.uint8)
    signed = np.zeros_like(source, dtype=np.uint8)
    luma_diff = gray(suspect) - gray(source)
    signed[..., 0] = np.clip(luma_diff * 12 + 128, 0, 255)
    signed[..., 1] = 128
    signed[..., 2] = np.clip(-luma_diff * 12 + 128, 0, 255)

    paths = {
        "abs_diff_x8": out_dir / "abs_diff_x8.png",
        "signed_luma_diff": out_dir / "signed_luma_diff_red_brighter_blue_darker.png",
    }
    Image.fromarray(abs_diff).save(paths["abs_diff_x8"])
    Image.fromarray(signed).save(paths["signed_luma_diff"])
    return {k: str(v) for k, v in paths.items()}


def analyze_pair(source_path: Path, suspect_path: Path, out_dir: Path) -> dict:
    source_image = Image.open(source_path).convert("RGB")
    suspect_image = Image.open(suspect_path).convert("RGB")
    if source_image.size != suspect_image.size:
        suspect_image = suspect_image.resize(source_image.size, Image.Resampling.BICUBIC)

    source = np.asarray(source_image).astype(np.float32)
    suspect = np.asarray(suspect_image).astype(np.float32)
    source_g = gray(source)
    suspect_g = gray(suspect)
    diff = suspect - source
    abs_diff = np.abs(diff)

    source_residual = residual_std(source_g)
    suspect_residual = residual_std(suspect_g)
    source_block = blockiness(source_g)
    suspect_block = blockiness(suspect_g)
    channel_fit = fit_channels(source, suspect)
    suspect_meta = image_meta(suspect_path)

    flags = []
    if all(0.94 <= row["gain"] <= 0.99 and row["offset"] < 0 for row in channel_fit):
        flags.append("global_channel_affine_darkening")
    if suspect_residual < source_residual * 0.9:
        flags.append("broad_high_frequency_residual_suppression")
    if suspect_block > source_block * 1.08:
        flags.append("jpeg_blockiness_increase")
    if float((abs_diff.max(axis=2) > 3).mean()) > 0.35 and all(row["correlation"] > 0.995 for row in channel_fit):
        flags.append("high_correlation_but_widespread_low_amplitude_changes")
    flags.extend(jpeg_rule_hits(suspect_meta))

    report = {
        "source": image_meta(source_path),
        "suspect": suspect_meta,
        "pair_metrics": {
            "same_size": source_image.size == suspect_image.size,
            "mean_diff_rgb": [round(float(v), 4) for v in diff.mean(axis=(0, 1))],
            "mean_abs_rgb": [round(float(v), 4) for v in abs_diff.mean(axis=(0, 1))],
            "median_abs_rgb": [round(float(v), 4) for v in np.median(abs_diff, axis=(0, 1))],
            "changed_gt3": round(float((abs_diff.max(axis=2) > 3).mean()), 6),
            "changed_gt10": round(float((abs_diff.max(axis=2) > 10).mean()), 6),
            "gray_diff_percentiles": [round(float(v), 4) for v in np.percentile(suspect_g - source_g, [1, 5, 25, 50, 75, 95, 99])],
            "residual_std_source": round(source_residual, 4),
            "residual_std_suspect": round(suspect_residual, 4),
            "laplacian_std_source": round(laplacian_std(source_g), 4),
            "laplacian_std_suspect": round(laplacian_std(suspect_g), 4),
            "blockiness_source": round(source_block, 4),
            "blockiness_suspect": round(suspect_block, 4),
            "channel_fit": channel_fit,
        },
        "regions": compare_regions(source, suspect),
        "defensive_flags": flags,
        "risk_score": min(100, len(flags) * 14),
        "heatmaps": save_heatmaps(source, suspect, out_dir),
    }
    return report


def write_markdown(report: dict, path: Path) -> None:
    metrics = report["pair_metrics"]
    lines = [
        "# Defensive Forensics Report",
        "",
        f"Risk score: **{report['risk_score']} / 100**",
        "",
        "## Defensive Flags",
        "",
    ]
    if report["defensive_flags"]:
        lines.extend(f"- `{flag}`" for flag in report["defensive_flags"])
    else:
        lines.append("- No rule hits.")
    lines.extend(
        [
            "",
            "## Pair Metrics",
            "",
            f"- Mean RGB shift: `{metrics['mean_diff_rgb']}`",
            f"- Mean absolute RGB delta: `{metrics['mean_abs_rgb']}`",
            f"- Changed pixels > 3: `{metrics['changed_gt3']}`",
            f"- Changed pixels > 10: `{metrics['changed_gt10']}`",
            f"- Residual std source/suspect: `{metrics['residual_std_source']}` / `{metrics['residual_std_suspect']}`",
            f"- Laplacian std source/suspect: `{metrics['laplacian_std_source']}` / `{metrics['laplacian_std_suspect']}`",
            f"- Blockiness source/suspect: `{metrics['blockiness_source']}` / `{metrics['blockiness_suspect']}`",
            "",
            "## Channel Fit",
            "",
            "| Channel | Gain | Offset | Correlation |",
            "|---|---:|---:|---:|",
        ]
    )
    for row in metrics["channel_fit"]:
        lines.append(f"| {row['channel']} | {row['gain']} | {row['offset']} | {row['correlation']} |")
    lines.extend(
        [
            "",
            "## JPEG Fingerprint",
            "",
            "```json",
            json.dumps(report["suspect"].get("jpeg", {}), indent=2, ensure_ascii=False),
            "```",
            "",
            "## Heatmaps",
            "",
        ]
    )
    for name, heatmap_path in report["heatmaps"].items():
        lines.append(f"- {name}: `{heatmap_path}`")
    path.write_text("\n".join(lines), encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description="Defensive forensic comparison for suspicious image post-processing.")
    parser.add_argument("--source", required=True, type=Path, help="Original or baseline image.")
    parser.add_argument("--suspect", required=True, type=Path, help="Suspicious transformed image.")
    parser.add_argument("--out-dir", default=Path("analysis_outputs/defensive_forensics"), type=Path)
    args = parser.parse_args()

    args.out_dir.mkdir(parents=True, exist_ok=True)
    report = analyze_pair(args.source, args.suspect, args.out_dir)
    json_path = args.out_dir / "report.json"
    md_path = args.out_dir / "report.md"
    json_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    write_markdown(report, md_path)
    print(f"Wrote {json_path}")
    print(f"Wrote {md_path}")
    print(f"Risk score: {report['risk_score']} / 100")
    print("Flags:")
    for flag in report["defensive_flags"]:
        print(f" - {flag}")


if __name__ == "__main__":
    main()
