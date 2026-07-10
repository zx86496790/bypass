from pathlib import Path
import io
import zipfile

from PIL import Image

import server


OUT = Path("analysis_outputs/current_audit")
OUT.mkdir(parents=True, exist_ok=True)

IMAGES = [
    ("snow_portrait", Path(r"C:/Users/zsen/Desktop/ig_059018b641d22072016a1e5314bee0819a9a837b923e86a889.png")),
    ("bridge_portrait", Path(r"C:/Users/zsen/Desktop/14d2ecbf-6236-4756-8ae9-28515853b1c8.png")),
    ("alley_portrait", Path(r"C:/Users/zsen/Desktop/Gemini_Generated_Image_wxk0h6wxk0h6wxk0.png")),
    ("night_rain_portrait", Path(r"C:/Users/zsen/Desktop/ChatGPT Image May 23, 2026, 11_33_55 PM.png")),
]


def write_image_outputs(label, path):
    image = Image.open(path).convert("RGB")
    auto = server.auto_route_settings(image, {"route": "auto", "autoRoute": True, "writeExif": False})
    processed = server.process(image, dict(auto))
    single_bytes = server.save_jpeg_bytes(processed, auto)
    single_path = OUT / f"audit-single-{label}.jpg"
    single_path.write_bytes(single_bytes)

    candidates = server.adaptive_candidate_settings(image, {"route": "auto", "autoRoute": True, "writeExif": False})
    zip_path = OUT / f"audit-candidates-{label}.zip"
    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for idx, (name, settings) in enumerate(candidates, start=1):
            output = server.process(image, settings)
            data = server.save_jpeg_bytes(output, settings)
            zf.writestr(f"{idx:02d}_{name}.jpg", data)

    return {
        "label": label,
        "input": str(path),
        "single": str(single_path.resolve()),
        "zip": str(zip_path.resolve()),
        "route": auto.get("route"),
        "reason": auto.get("autoReason"),
        "candidate_count": len(candidates),
        "candidate_names": [name for name, _ in candidates],
        "auto_settings": {k: v for k, v in auto.items() if k != "autoProfile"},
        "profile": auto.get("autoProfile"),
    }


if __name__ == "__main__":
    for item in IMAGES:
        result = write_image_outputs(*item)
        print("===", result["label"], "===")
        print("reason:", result["reason"])
        print("route:", result["route"])
        print("single:", result["single"])
        print("zip:", result["zip"])
        print("candidates:", result["candidate_count"])
        for idx, name in enumerate(result["candidate_names"], start=1):
            print(f"{idx:02d}", name)
