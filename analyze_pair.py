from pathlib import Path
from PIL import Image, ImageStat, ExifTags
import numpy as np


pairs = {
    "bridge_30": (
        Path(r"C:/Users/zsen/Desktop/14d2ecbf-6236-4756-8ae9-28515853b1c8.png"),
        Path(r"C:/Users/zsen/Downloads/phlegethon-forged-J7pBbVotGur7v5VlJZseI.jpg"),
    ),
    "snow_16": (
        Path(r"C:/Users/zsen/Desktop/ig_059018b641d22072016a1e5314bee0819a9a837b923e86a889.png"),
        Path(r"C:/Users/zsen/Downloads/phlegethon_ig_059018b641d22072016a1e5314bee0819a9a837b923e86a889.png.jpg"),
    ),
    "alley_89": (
        Path(r"C:/Users/zsen/Desktop/Gemini_Generated_Image_wxk0h6wxk0h6wxk0.png"),
        Path(r"C:/Users/zsen/Downloads/phlegethon-forged-yVT9v5yqE2Z-7ZzfvUR-M.jpg"),
    ),
}


def gray(arr):
    arr = arr.astype(np.float32)
    return arr[..., 0] * 0.299 + arr[..., 1] * 0.587 + arr[..., 2] * 0.114


def residual_std(g):
    center = g[1:-1, 1:-1]
    nb = (g[:-2, 1:-1] + g[2:, 1:-1] + g[1:-1, :-2] + g[1:-1, 2:]) / 4
    return float((center - nb).std())


def blockiness(g):
    vx = g[:, 8::8]
    vy = g[:, 7::8]
    hx = g[8::8, :]
    hy = g[7::8, :]
    v = np.abs(vx[:, : vy.shape[1]] - vy[:, : vx.shape[1]]).mean() if g.shape[1] > 8 else 0
    h = np.abs(hx[: hy.shape[0], :] - hy[: hx.shape[0], :]).mean() if g.shape[0] > 8 else 0
    return float((v + h) / 2)


def print_meta(label, p):
    im = Image.open(p)
    print(f"\n{label} {p}")
    print(" format", im.format, "mode", im.mode, "size", im.size, "bytes", p.stat().st_size)
    print(" info", {k: (f"<{len(v)} bytes>" if isinstance(v, bytes) else v) for k, v in im.info.items()})
    exif = im.getexif()
    print(" exif_count", len(exif))
    for k in [271, 272, 305, 306, 282, 283, 33434, 33437, 34855, 37386, 40961]:
        if exif.get(k) is not None:
            print("  ", ExifTags.TAGS.get(k, k), repr(exif.get(k))[:160])
    stat = ImageStat.Stat(im.convert("RGB"))
    print(" mean", [round(x, 2) for x in stat.mean], "std", [round(x, 2) for x in stat.stddev])
    if im.format == "JPEG":
        print(" jpeg_layers", getattr(im, "layers", None), "layer", getattr(im, "layer", None))
        print(" quant_tables", {k: (sum(v), v[:8]) for k, v in im.quantization.items()})


def analyze_pair(name, src_path, out_path):
    print("\n" + "=" * 70)
    print("PAIR", name)
    print_meta("source", src_path)
    print_meta("forged", out_path)

    src = np.asarray(Image.open(src_path).convert("RGB")).astype(np.int16)
    out = np.asarray(Image.open(out_path).convert("RGB")).astype(np.int16)
    print("same_size", src.shape == out.shape)
    d = out - src
    ad = np.abs(d)
    gs, go = gray(src), gray(out)
    gd = go - gs
    print("mean_diff_rgb forged-source", d.mean(axis=(0, 1)).round(3).tolist())
    print("mean_abs_rgb", ad.mean(axis=(0, 1)).round(3).tolist())
    print("median_abs_rgb", np.median(ad, axis=(0, 1)).round(3).tolist())
    print("max_abs_rgb", ad.max(axis=(0, 1)).tolist())
    print("changed_gt3", float((ad.max(axis=2) > 3).mean()))
    print("changed_gt10", float((ad.max(axis=2) > 10).mean()))
    print("gray_mean", float(gd.mean()), "gray_abs", float(np.abs(gd).mean()))
    print("gray_percentiles", np.percentile(gd, [1, 5, 25, 50, 75, 95, 99]).round(3).tolist())
    print("residual_std source/forged/diff", round(residual_std(gs), 4), round(residual_std(go), 4), round(residual_std(gd), 4))
    print("blockiness source/forged", round(blockiness(gs), 4), round(blockiness(go), 4))

    h, w = gs.shape
    regions = {
        "sky_top": (0, 0, w, int(h * 0.25)),
        "center_subject": (int(w * 0.45), int(h * 0.35), int(w * 0.85), int(h * 0.9)),
        "left_road": (0, int(h * 0.45), int(w * 0.38), int(h * 0.9)),
        "right_rail": (int(w * 0.72), int(h * 0.48), w, h),
        "dark_bottom": (0, int(h * 0.75), w, h),
    }
    print("regions")
    for rname, (x0, y0, x1, y1) in regions.items():
        rr = d[y0:y1, x0:x1]
        gr = gd[y0:y1, x0:x1]
        print(
            " ",
            rname,
            "mean_rgb",
            rr.mean(axis=(0, 1)).round(2).tolist(),
            "abs_rgb",
            np.abs(rr).mean(axis=(0, 1)).round(2).tolist(),
            "gray_mean",
            round(float(gr.mean()), 2),
            "gray_abs",
            round(float(np.abs(gr).mean()), 2),
            "resid_src/out",
            round(residual_std(gs[y0:y1, x0:x1]), 3),
            round(residual_std(go[y0:y1, x0:x1]), 3),
        )

    out_dir = Path("analysis_outputs") / name
    out_dir.mkdir(parents=True, exist_ok=True)
    diff_vis = np.clip(ad * 8, 0, 255).astype(np.uint8)
    Image.fromarray(diff_vis).save(out_dir / "abs_diff_x8.png")
    signed = np.zeros_like(src, dtype=np.uint8)
    mean_d = d.mean(axis=2)
    signed[..., 0] = np.clip(mean_d * 12 + 128, 0, 255)
    signed[..., 1] = 128
    signed[..., 2] = np.clip(-mean_d * 12 + 128, 0, 255)
    Image.fromarray(signed).save(out_dir / "signed_diff_red_forged_brighter_blue_darker.png")


for name, (src_path, out_path) in pairs.items():
    if not src_path.exists() or not out_path.exists():
        print("\n" + "=" * 70)
        print("SKIP", name, "missing file")
        print(" source", src_path, src_path.exists())
        print(" forged", out_path, out_path.exists())
        continue
    analyze_pair(name, src_path, out_path)
