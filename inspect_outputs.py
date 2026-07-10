from pathlib import Path
from PIL import Image
import numpy as np

paths = [
    Path(r"C:/Users/zsen/Downloads/texture-lab-output (2).jpg"),
    Path(r"C:/Users/zsen/Downloads/phlegethon-forged-J7pBbVotGur7v5VlJZseI.jpg"),
    Path(r"C:/Users/zsen/Desktop/14d2ecbf-6236-4756-8ae9-28515853b1c8.png"),
]

for p in paths:
    im = Image.open(p)
    print("\nFILE", p)
    print("format", im.format, "size", im.size, "bytes", p.stat().st_size, "info", list(im.info.keys()))
    print("exif_count", len(im.getexif()))
    if im.format == "JPEG":
        print("layer", getattr(im, "layer", None))
        print("qtables", {k: (sum(v), v[:8]) for k, v in im.quantization.items()})

orig = np.asarray(Image.open(paths[2]).convert("RGB")).astype(int)
for label, p in [("ours", paths[0]), ("phlegethon", paths[1])]:
    arr = np.asarray(Image.open(p).convert("RGB")).astype(int)
    d = arr - orig
    print("\nDIFF", label)
    print("mean", d.mean(axis=(0, 1)).round(3).tolist())
    print("abs", np.abs(d).mean(axis=(0, 1)).round(3).tolist())
    print("gt10", float((np.abs(d).max(axis=2) > 10).mean()))

