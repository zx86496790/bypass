from pathlib import Path
import json
import zipfile

from PIL import Image

from server import candidate_settings, process, save_jpeg_bytes


DOWNLOADS = Path(r"C:/Users/zsen/Downloads")
SOURCES = [
    (
        "night_snow_portrait_routeB",
        Path(r"C:/Users/zsen/Desktop/ae79f564-9331-477c-bf68-7982e0139710.jpg"),
    ),
    (
        "alley_snow_portrait_routeB",
        Path(r"C:/Users/zsen/Desktop/Gemini_Generated_Image_wxk0h6wxk0h6wxk0.png"),
    ),
]


def write_pack(label, source):
    image = Image.open(source).convert("RGB")
    output_path = DOWNLOADS / f"truthscan-candidates-{label}.zip"
    manifest = []
    with zipfile.ZipFile(output_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for idx, (name, settings) in enumerate(candidate_settings({}), start=1):
            output = process(image, settings)
            data = save_jpeg_bytes(output, settings)
            filename = f"{idx:02d}_{name}.jpg"
            zf.writestr(filename, data)
            manifest.append({"file": filename, "settings": settings, "bytes": len(data)})
        zf.writestr("manifest.json", json.dumps(manifest, ensure_ascii=False, indent=2))
        zf.writestr(
            "README.txt",
            "Candidate 01 is the old bridge baseline. Candidates 02-24 are Route B reconstruction candidates.\n",
        )
    return output_path


def main():
    for label, source in SOURCES:
        path = write_pack(label, source)
        print(path)


if __name__ == "__main__":
    main()
