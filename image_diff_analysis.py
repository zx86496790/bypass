from pathlib import Path
from PIL import Image, ImageOps, ImageEnhance, ExifTags
import numpy as np

OUT = Path("analysis_outputs")
OUT.mkdir(exist_ok=True)

img1_path = Path(r"C:/Users/zsen/Downloads/phlegethon_ig_059018b641d22072016a1e5314bee0819a9a837b923e86a889.png.jpg")
img2_path = Path(r"C:/Users/zsen/Desktop/ig_059018b641d22072016a1e5314bee0819a9a837b923e86a889.png")

im1 = Image.open(img1_path).convert("RGB")
im2 = Image.open(img2_path).convert("RGB")
a = np.asarray(im1).astype(np.int16)
b = np.asarray(im2).astype(np.int16)
d = a - b
ad = np.abs(d)

def gray(x):
    x = x.astype(np.float32)
    return 0.299 * x[..., 0] + 0.587 * x[..., 1] + 0.114 * x[..., 2]

g1, g2 = gray(a), gray(b)
gd = g1 - g2

print("FILES")
for label, p in [("image1", img1_path), ("image2", img2_path)]:
    im = Image.open(p)
    print(label, p)
    print(" format", im.format, "mode", im.mode, "size", im.size, "bytes", p.stat().st_size)
    print(" info", {k: ("<%d bytes>" % len(v) if isinstance(v, bytes) else v) for k, v in im.info.items()})
    exif = im.getexif()
    if exif:
        print(" exif")
        for k, v in exif.items():
            print("  ", ExifTags.TAGS.get(k, k), repr(v)[:160])

print("\nGLOBAL_DIFF image1 - image2")
print("mean_rgb", d.mean(axis=(0,1)).round(3).tolist())
print("mean_abs_rgb", ad.mean(axis=(0,1)).round(3).tolist())
print("median_abs_rgb", np.median(ad, axis=(0,1)).round(3).tolist())
print("max_abs_rgb", ad.max(axis=(0,1)).tolist())
print("changed_pixels_abs_gt_3", float((ad.max(axis=2) > 3).mean()))
print("changed_pixels_abs_gt_10", float((ad.max(axis=2) > 10).mean()))
print("gray_mean_diff", float(gd.mean()), "gray_abs_mean", float(np.abs(gd).mean()))
print("gray_percentiles", np.percentile(gd, [1,5,25,50,75,95,99]).round(3).tolist())

regions = {
    "sky_top": (0, 0, 1086, 320),
    "hair": (210, 300, 610, 670),
    "face": (365, 480, 655, 770),
    "scarf": (260, 690, 745, 930),
    "coat": (160, 830, 880, 1448),
    "building": (620, 330, 1086, 850),
    "snow_ground": (600, 820, 1086, 1250),
}
print("\nREGIONS")
for name, (x0,y0,x1,y1) in regions.items():
    rr = d[y0:y1, x0:x1]
    ar = np.abs(rr)
    gr = gd[y0:y1, x0:x1]
    print(name, "mean_rgb", rr.mean(axis=(0,1)).round(2).tolist(),
          "abs_rgb", ar.mean(axis=(0,1)).round(2).tolist(),
          "gray_mean", round(float(gr.mean()), 2),
          "gray_abs", round(float(np.abs(gr).mean()), 2))

def neighbor_residual(arr):
    arr = arr.astype(np.float32)
    center = arr[1:-1, 1:-1]
    nb = (arr[:-2,1:-1] + arr[2:,1:-1] + arr[1:-1,:-2] + arr[1:-1,2:]) / 4.0
    return center - nb

print("\nLOCAL_NOISE_RESIDUAL_STD gray")
for label, g in [("image1", g1), ("image2", g2), ("diff", gd)]:
    print(label, round(float(neighbor_residual(g).std()), 4))
for name, (x0,y0,x1,y1) in regions.items():
    print(name, "img1", round(float(neighbor_residual(g1[y0:y1,x0:x1]).std()), 4),
          "img2", round(float(neighbor_residual(g2[y0:y1,x0:x1]).std()), 4),
          "diff", round(float(neighbor_residual(gd[y0:y1,x0:x1]).std()), 4))

# Visual artifacts.
diff_vis = np.clip(ad * 8, 0, 255).astype(np.uint8)
Image.fromarray(diff_vis).save(OUT / "abs_diff_x8.png")
signed = np.zeros_like(a, dtype=np.uint8)
signed[..., 0] = np.clip(-d.mean(axis=2) * 12 + 128, 0, 255)
signed[..., 1] = 128
signed[..., 2] = np.clip(d.mean(axis=2) * 12 + 128, 0, 255)
Image.fromarray(signed).save(OUT / "signed_diff_blue_image1_brighter_red_image1_darker.png")

crop_boxes = {
    "face": (330, 430, 700, 820),
    "hair": (190, 270, 665, 690),
    "building_lamps": (620, 430, 1086, 900),
    "coat_scarf": (140, 650, 900, 1300),
}
for name, box in crop_boxes.items():
    im1.crop(box).save(OUT / f"{name}_image1.jpg", quality=95)
    im2.crop(box).save(OUT / f"{name}_image2.png")
    Image.fromarray(diff_vis[box[1]:box[3], box[0]:box[2]]).save(OUT / f"{name}_abs_diff_x8.png")

