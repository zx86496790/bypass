from pathlib import Path
from PIL import Image


paths = [
    Path(r"C:/Users/zsen/Downloads/texture-lab-output.jpg"),
    Path(r"C:/Users/zsen/Downloads/texture-lab-output (1).jpg"),
]

for p in paths:
    im = Image.open(p)
    print("\nFILE", p)
    print("format", im.format, "size", im.size, "bytes", p.stat().st_size)
    print("info", list(im.info.keys()), "exif", len(im.getexif()))
    if im.format == "JPEG":
        print("qtables", {k: (sum(v), v[:8]) for k, v in im.quantization.items()})
        print("layer", getattr(im, "layer", None))

