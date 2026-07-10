from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse
import base64
import io
import json
import mimetypes
import uuid
import zipfile

import numpy as np
from PIL import Image, ImageFilter, ImageOps, TiffImagePlugin

from defensive_forensics import analyze_pair as analyze_forensics_pair


ROOT = Path(__file__).resolve().parent
CAL_INPUT = Path(r"C:/Users/zsen/Desktop/ig_059018b641d22072016a1e5314bee0819a9a837b923e86a889.png")
CAL_OUTPUT = Path(r"C:/Users/zsen/Downloads/phlegethon_ig_059018b641d22072016a1e5314bee0819a9a837b923e86a889.png.jpg")
PHLEGETHON_REFERENCE = Path(r"C:/Users/zsen/Downloads/phlegethon-forged-bA0TPQiMp8h1DW1MMFc0U.jpg")
REAL_DONOR_PATHS = [
    Path(r"C:/Users/zsen/Desktop/照片/88354f0dbad2a307a391722f5dd1e22c.PNG"),
    Path(r"C:/Users/zsen/Desktop/照片/IMG_3617.PNG"),
    Path(r"C:/Users/zsen/Desktop/照片/IMG_4113.jpg"),
    Path(r"C:/Users/zsen/Desktop/照片/IMG_8704.jpg"),
    Path(r"C:/Users/zsen/Desktop/照片/IMG_9412.png"),
    Path(r"C:/Users/zsen/Desktop/照片/IMG_9414.png"),
    Path(r"C:/Users/zsen/Desktop/照片/IMG_9630.png"),
    Path(r"C:/Users/zsen/Desktop/照片/屏幕截图 2026-02-20 224720.png"),
]
AFFINE = np.array(
    [
        [0.97088, -0.153],
        [0.96920, -0.714],
        [0.96408, 1.345],
    ],
    dtype=np.float32,
)
PHLEGETHON_MIMIC_AFFINE = np.array(
    [
        [0.967461, -1.668849],
        [0.970711, -1.374864],
        [0.970294, -1.336976],
    ],
    dtype=np.float32,
)
PHLEGETHON_QTABLES = [
    [
        3, 2, 2, 3, 4, 6, 8, 10,
        2, 2, 2, 3, 4, 9, 10, 9,
        2, 2, 3, 4, 6, 9, 11, 9,
        2, 3, 4, 5, 8, 14, 13, 10,
        3, 4, 6, 9, 11, 17, 16, 12,
        4, 6, 9, 10, 13, 17, 18, 15,
        8, 10, 12, 14, 16, 19, 19, 16,
        12, 15, 15, 16, 18, 16, 16, 16,
    ],
    [
        3, 3, 4, 8, 16, 16, 16, 16,
        3, 3, 4, 11, 16, 16, 16, 16,
        4, 4, 9, 16, 16, 16, 16, 16,
        8, 11, 16, 16, 16, 16, 16, 16,
        16, 16, 16, 16, 16, 16, 16, 16,
        16, 16, 16, 16, 16, 16, 16, 16,
        16, 16, 16, 16, 16, 16, 16, 16,
        16, 16, 16, 16, 16, 16, 16, 16,
    ],
]
_cal_input_array = None
_cal_residual = None


def calibration_input_array():
    global _cal_input_array
    if _cal_input_array is None:
        _cal_input_array = np.asarray(Image.open(CAL_INPUT).convert("RGB"))
    return _cal_input_array


def calibration_residual():
    global _cal_residual
    if _cal_residual is None:
        src = np.asarray(Image.open(CAL_INPUT).convert("RGB")).astype(np.float32)
        dst = np.asarray(Image.open(CAL_OUTPUT).convert("RGB")).astype(np.float32)
        base = src.copy()
        base[..., 0] = base[..., 0] * AFFINE[0, 0] + AFFINE[0, 1]
        base[..., 1] = base[..., 1] * AFFINE[1, 0] + AFFINE[1, 1]
        base[..., 2] = base[..., 2] * AFFINE[2, 0] + AFFINE[2, 1]
        _cal_residual = dst - np.clip(base, 0, 255)
    return _cal_residual


def noise(width, height, seed):
    y, x = np.mgrid[0:height, 0:width]
    n = np.sin(x * 12.9898 + y * 78.233 + seed * 37.719) * 43758.5453
    return n - np.floor(n)


def donor_patch(width, height, seed):
    existing = [p for p in REAL_DONOR_PATHS if p.exists()]
    if not existing:
        return None
    path = existing[int(seed) % len(existing)]
    donor = ImageOps.exif_transpose(Image.open(path)).convert("RGB")
    dw, dh = donor.size
    target_aspect = width / max(1, height)
    donor_aspect = dw / max(1, dh)
    if donor_aspect > target_aspect:
        crop_w = max(1, round(dh * target_aspect))
        max_x = max(0, dw - crop_w)
        x = int(noise(1, 1, seed + 101)[0, 0] * max_x)
        box = (x, 0, x + crop_w, dh)
    else:
        crop_h = max(1, round(dw / target_aspect))
        max_y = max(0, dh - crop_h)
        y = int(noise(1, 1, seed + 103)[0, 0] * max_y)
        box = (0, y, dw, y + crop_h)
    donor = donor.crop(box).resize((width, height), Image.Resampling.BICUBIC)
    return np.asarray(donor).astype(np.float32)


def normalized_residual(arr, radius=1.2):
    blur = local_blur_array(arr, radius)
    resid = arr - blur
    std = float(np.std(resid))
    if std < 1e-3:
        return resid
    return resid / std


def edge_strength(rgb):
    lum = rgb[..., 0] * 0.299 + rgb[..., 1] * 0.587 + rgb[..., 2] * 0.114
    left = np.pad(lum[:, :-1], ((0, 0), (1, 0)), mode="edge")
    right = np.pad(lum[:, 1:], ((0, 0), (0, 1)), mode="edge")
    up = np.pad(lum[:-1, :], ((1, 0), (0, 0)), mode="edge")
    down = np.pad(lum[1:, :], ((0, 1), (0, 0)), mode="edge")
    center = lum
    gx = np.abs(left - right)
    gy = np.abs(up - down)
    local = np.abs(center - (left + right + up + down) / 4)
    return np.clip((gx + gy) / 80 + local / 90, 0, 1)


def residual_std_gray(lum):
    if lum.shape[0] < 3 or lum.shape[1] < 3:
        return 0.0
    center = lum[1:-1, 1:-1]
    nb = (lum[:-2, 1:-1] + lum[2:, 1:-1] + lum[1:-1, :-2] + lum[1:-1, 2:]) / 4
    return float((center - nb).std())


def image_profile(image):
    rgb = np.asarray(image.convert("RGB")).astype(np.float32)
    lum = rgb[..., 0] * 0.299 + rgb[..., 1] * 0.587 + rgb[..., 2] * 0.114
    edge = edge_strength(rgb)
    smooth = np.clip(1.0 - edge * 1.8, 0, 1)
    cold = np.clip((rgb[..., 2] - rgb[..., 0] + 18) / 95, 0, 1)
    bright = np.clip((lum - 55) / 155, 0, 1)
    dark = np.clip((85 - lum) / 85, 0, 1)
    saturation = rgb.max(axis=2) - rgb.min(axis=2)
    r, g, b = rgb[..., 0], rgb[..., 1], rgb[..., 2]
    skin = (
        (r > 64) & (g > 38) & (b > 25) &
        (r > b * 0.86) & (g > b * 0.66) &
        (lum > 35) & (lum < 190) & (saturation < 125)
    )
    h, w = lum.shape
    mid_skin = skin[round(h * 0.18):round(h * 0.72), round(w * 0.22):round(w * 0.78)]
    return {
        "mean_lum": float(lum.mean()),
        "std_lum": float(lum.std()),
        "edge_mean": float(edge.mean()),
        "smooth_ratio": float((smooth > 0.68).mean()),
        "bright_smooth_ratio": float(((smooth > 0.68) & (lum > 120)).mean()),
        "cold_ratio": float((cold > 0.62).mean()),
        "snow_cold_ratio": float(((cold > 0.62) & (lum > 105) & (saturation < 72)).mean()),
        "dark_ratio": float((dark > 0.45).mean()),
        "residual_std": residual_std_gray(lum),
        "skin_ratio": float(skin.mean()),
        "mid_skin_ratio": float(mid_skin.mean()) if mid_skin.size else 0.0,
    }


def auto_route_settings(image, settings):
    profile = image_profile(image)
    route = "A"
    reason = "camera_residual"

    if profile["mean_lum"] < 66 and profile["dark_ratio"] > 0.48 and profile["smooth_ratio"] > 0.84 and profile["mid_skin_ratio"] > 0.22 and profile["residual_std"] < 2.8:
        route = "O"
        reason = "close_smooth_dark_face_portrait"
    elif profile["mean_lum"] < 70 and profile["dark_ratio"] > 0.48 and profile["cold_ratio"] > 0.30 and profile["bright_smooth_ratio"] > 0.12 and profile["residual_std"] < 3.4:
        route = "B"
        reason = "cold_dark_snow_portrait"
    elif profile["mean_lum"] < 62 and profile["dark_ratio"] > 0.50 and profile["smooth_ratio"] > 0.78 and profile["residual_std"] < 2.8:
        route = "E"
        reason = "dark_smooth_low_residual_surface"
    elif profile["mean_lum"] < 72 and profile["dark_ratio"] > 0.42 and profile["smooth_ratio"] > 0.74 and profile["cold_ratio"] < 0.08 and profile["residual_std"] < 4.0:
        route = "E"
        reason = "warm_indoor_flash_smooth_surface"
    elif profile["bright_smooth_ratio"] > 0.18 and profile["cold_ratio"] > 0.30 and profile["smooth_ratio"] > 0.78 and profile["residual_std"] < 2.8:
        route = "E"
        reason = "bright_cold_smooth_low_residual_surface"
    elif profile["smooth_ratio"] > 0.82 and profile["residual_std"] < 2.4 and profile["cold_ratio"] < 0.30 and profile["bright_smooth_ratio"] > 0.25:
        route = "A"
        reason = "bridge_like_camera_residual"
    elif profile["smooth_ratio"] > 0.82 and profile["residual_std"] < 2.4:
        route = "C"
        reason = "ultra_smooth_low_residual_surface"
    elif profile["snow_cold_ratio"] > 0.30 and profile["bright_smooth_ratio"] > 0.30 and profile["residual_std"] < 4.2:
        route = "A"
        reason = "sharp_snow_camera_residual"
    elif profile["edge_mean"] > 0.22 and profile["residual_std"] > 4.7 and profile["smooth_ratio"] < 0.55 and profile["dark_ratio"] > 0.22:
        route = "I"
        reason = "high_detail_alley_portrait"
    elif profile["snow_cold_ratio"] > 0.30 and profile["dark_ratio"] > 0.25:
        route = "D"
        reason = "cold_snow_portrait_strong"
    elif profile["snow_cold_ratio"] > 0.18 and profile["bright_smooth_ratio"] > 0.18:
        route = "D"
        reason = "cold_snow_background"
    elif profile["residual_std"] > 5.6 and profile["edge_mean"] > 0.13:
        route = "C"
        reason = "high_texture_semantic_risk"
    elif profile["residual_std"] > 5.1 and profile["smooth_ratio"] > 0.45:
        route = "C"
        reason = "high_existing_texture_needs_suppression"
    elif profile["bright_smooth_ratio"] > 0.22 and profile["cold_ratio"] > 0.36:
        route = "D"
        reason = "cold_bright_background"
    elif profile["mean_lum"] < 78 and profile["dark_ratio"] > 0.38:
        route = "B"
        reason = "low_light_texture_rebuild"
    elif profile["edge_mean"] < 0.10 and profile["smooth_ratio"] > 0.58:
        route = "C"
        reason = "over_smooth_ai_surface"

    selected = dict(settings)
    selected["autoProfile"] = profile
    selected["autoReason"] = reason
    if route == "A":
        selected.update({
            "route": "A",
            "calibrated": True,
            "phlegethonLight": True,
            "writeExif": False,
            "lumaNoise": 18,
            "chromaScale": 1.2,
            "residualScale": 1.0,
            "truthscanStrength": 1.0,
        })
        if reason == "bridge_like_camera_residual":
            selected.update({
                "lumaNoise": 18,
                "chromaScale": 1.2,
                "residualScale": 1.0,
                "resample": 0,
                "doubleJpeg": False,
            })
        elif reason == "sharp_snow_camera_residual":
            selected.update({
                "route": "I",
                "routeIBaseLuma": 36,
                "routeIBaseResample": 1.0,
                "routeIBaseBlend": 0.45,
                "routeIBasePixelScale": 1.2,
                "routeIBaseMicroShift": 0.12,
                "routeIBasePrnu": 0.18,
                "routeIBaseRow": 0.18,
                "routeIBaseSharpen": 0.18,
                "routeIRotate": 0.08,
                "routeIOpticalScale": 1.5,
                "routeILensShade": 0.12,
                "routeIChromaticAberration": 0.05,
                "routeILocalContrast": 0.03,
                "routeISeed": 701,
                "doubleJpeg": False,
            })
    elif route == "C":
        selected.update({
            "route": "C",
            "writeExif": False,
        })
        if reason == "cold_dark_snow_portrait":
            selected.update({
                "routeCDenoise": 1.35,
                "routeCEdgeProtect": 2.06,
                "routeCHighKeep": 0.18,
                "routeCMidKeep": 0.48,
                "routeCBackgroundDark": 5.9,
                "routeCResidualFloor": 0.045,
                "routeCBlock": 0.10,
                "routeCChroma": 0.24,
                "routeCResample": 4,
                "routeCSeed": 317,
                "autoChannel": "coldSnowC_smooth_rebuild",
                "autoDecision": (
                    "cold/dark snow portrait: "
                    f"cold={profile['cold_ratio']:.3f}, "
                    f"bright_smooth={profile['bright_smooth_ratio']:.3f}, "
                    f"dark={profile['dark_ratio']:.3f}"
                ),
            })
        elif reason == "ultra_smooth_low_residual_surface":
            smooth_push = np.clip((profile["smooth_ratio"] - 0.75) / 0.25, 0, 1)
            low_residual_push = np.clip((2.8 - profile["residual_std"]) / 2.8, 0, 1)
            cold_push = np.clip((profile["cold_ratio"] - 0.25) / 0.5, 0, 1)
            selected.update({
                "routeCDenoise": float(1.52 + smooth_push * 0.05),
                "routeCEdgeProtect": float(np.clip(1.68 + profile["dark_ratio"] * 1.18, 2.02, 2.09)),
                "routeCHighKeep": float(np.clip(0.154 - low_residual_push * 0.008, 0.148, 0.152)),
                "routeCMidKeep": float(0.445 - smooth_push * 0.010),
                "routeCBackgroundDark": float(5.55 + profile["bright_smooth_ratio"] * 0.45 + cold_push * 0.12),
                "routeCResidualFloor": float(max(0.048, 0.055 - low_residual_push * 0.007)),
                "routeCBlock": float(max(0.095, 0.110 - low_residual_push * 0.014)),
                "routeCChroma": float(0.235 + cold_push * 0.025),
                "routeCResample": 4,
                "routeCSeed": 317,
            })
        elif reason == "high_texture_semantic_risk":
            selected.update({
                "routeCDenoise": 1.25,
                "routeCHighKeep": 0.25,
                "routeCMidKeep": 0.52,
                "routeCBackgroundDark": 5.2,
                "routeCResidualFloor": 0.05,
                "routeCBlock": 0.15,
                "routeCChroma": 0.25,
                "routeCResample": 3,
            })
        else:
            selected.update({
                "routeCDenoise": 0.95,
                "routeCHighKeep": 0.38,
                "routeCMidKeep": 0.60,
                "routeCBackgroundDark": 4.8,
                "routeCResidualFloor": 0.18,
                "routeCBlock": 0.7,
                "routeCChroma": 0.45,
            })
    elif route == "O":
        selected.update({
            "route": "O",
            "writeExif": False,
            "doubleJpeg": False,
            "routeOSkinIrregular": 1.25,
            "routeORelight": 0.75,
            "routeOHair": 1.2,
            "routeOBg": 1.1,
            "routeOCfa": 0.45,
            "routeOClarity": 0.75,
            "routeOUnsharp": 65,
            "routeOSeed": 4107,
        })
    elif route == "E":
        if reason == "cold_dark_snow_portrait":
            selected.update({
                "route": "E",
                "writeExif": False,
                "doubleJpeg": True,
                "routeEShotNoise": 0.022,
                "routeEReadNoise": 0.0065,
                "routeEFixedNoise": 0.0026,
                "routeEDenoise": 0.55,
                "routeESharpen": 0.11,
                "routeECcm": 0.055,
                "routeEToe": 0.018,
                "routeEShoulder": 0.035,
                "routeEResample": 4,
                "routeEHighlightBloom": 0.0,
                "routeESeed": 557,
                "autoChannel": "coldSnowE_pseudo_raw_double",
                "autoDecision": (
                    "cold/dark snow portrait: "
                    f"cold={profile['cold_ratio']:.3f}, "
                    f"bright_smooth={profile['bright_smooth_ratio']:.3f}, "
                    f"dark={profile['dark_ratio']:.3f}"
                ),
            })
        elif reason == "dark_smooth_low_residual_surface":
            if profile["bright_smooth_ratio"] > 0.10 and profile["std_lum"] > 60:
                selected.update({
                    "route": "E",
                    "writeExif": False,
                    "doubleJpeg": False,
                    "routeEShotNoise": 0.018,
                    "routeEReadNoise": 0.0050,
                    "routeEFixedNoise": 0.0014,
                    "routeEDenoise": 0.70,
                    "routeESharpen": 0.050,
                    "routeECcm": 0.045,
                    "routeEToe": 0.018,
                    "routeEShoulder": 0.028,
                    "routeEResample": 5,
                    "routeERecaptureLongEdge": 720,
                    "routeEPostUnsharp": 45,
                    "routeEHighlightBloom": 0.035,
                    "routeEHighlightBlur": 4.5,
                    "routeESeed": 521,
                    "autoChannel": "darkE_window_recap720_score",
                    "autoDecision": (
                        "window/high-contrast dark profile: "
                        f"bright_smooth={profile['bright_smooth_ratio']:.3f}, "
                        f"std_lum={profile['std_lum']:.1f}"
                    ),
                })
            else:
                selected.update({
                    "route": "E",
                    "writeExif": False,
                    "doubleJpeg": True,
                    "routeEShotNoise": 0.018,
                    "routeEReadNoise": 0.0050,
                    "routeEFixedNoise": 0.0014,
                    "routeEDenoise": 0.70,
                    "routeESharpen": 0.050,
                    "routeECcm": 0.045,
                    "routeEToe": 0.018,
                    "routeEShoulder": 0.035,
                    "routeEResample": 5,
                    "routeEForceWidth": 1024,
                    "routeEForceHeight": 1536,
                    "routeEHighlightBloom": 0.0,
                    "routeESeed": 521,
                    "autoChannel": "darkE_score_recap_1024",
                    "autoDecision": (
                        "low-bright dark profile: "
                        f"bright_smooth={profile['bright_smooth_ratio']:.3f}, "
                        f"std_lum={profile['std_lum']:.1f}"
                    ),
                })
        elif reason == "bright_cold_smooth_low_residual_surface":
            selected.update({
                "route": "E",
                "writeExif": False,
                "doubleJpeg": False,
                "routeEShotNoise": 0.020,
                "routeEReadNoise": 0.0060,
                "routeEFixedNoise": 0.0025,
                "routeEDenoise": 0.55,
                "routeESharpen": 0.10,
                "routeECcm": 0.055,
                "routeEToe": 0.018,
                "routeEShoulder": 0.035,
                "routeEResample": 4,
                "routeEHighlightBloom": 0.0,
                "routeESeed": 509,
            })
        elif reason == "sharp_cold_snow_smooth_surface":
            selected.update({
                "route": "E",
                "writeExif": False,
                "doubleJpeg": False,
                "routeEShotNoise": 0.020,
                "routeEReadNoise": 0.0060,
                "routeEFixedNoise": 0.0025,
                "routeEDenoise": 0.55,
                "routeESharpen": 0.10,
                "routeECcm": 0.055,
                "routeEToe": 0.018,
                "routeEShoulder": 0.035,
                "routeEResample": 4,
                "routeEHighlightBloom": 0.0,
                "routeESeed": 509,
            })
        elif reason == "warm_indoor_flash_smooth_surface":
            selected.update({
                "route": "E",
                "writeExif": False,
                "doubleJpeg": False,
                "routeEShotNoise": 0.020,
                "routeEReadNoise": 0.0054,
                "routeEFixedNoise": 0.0012,
                "routeEDenoise": 0.76,
                "routeESharpen": 0.055,
                "routeECcm": 0.035,
                "routeEToe": 0.024,
                "routeEShoulder": 0.026,
                "routeEResample": 4,
                "routeEHighlightBloom": 0.025,
                "routeESeed": 541,
            })
        else:
            selected.update({
                "route": "E",
                "writeExif": False,
                "doubleJpeg": False,
                "routeEShotNoise": 0.018,
                "routeEReadNoise": 0.0052,
                "routeEFixedNoise": 0.0016,
                "routeEDenoise": 0.70,
                "routeESharpen": 0.055,
                "routeECcm": 0.045,
                "routeEToe": 0.018,
                "routeEShoulder": 0.028,
                "routeEResample": 4,
                "routeEHighlightBloom": 0.035,
                "routeESeed": 509,
            })
    elif route == "I":
        selected.update({
            "route": "P" if reason == "high_detail_alley_portrait" else "I",
            "writeExif": False,
            "routeIBaseLuma": 36 if reason == "cold_dark_snow_portrait" else 24,
            "routeIBaseResample": 1.0 if reason == "cold_dark_snow_portrait" else 0.5,
            "routeIBaseBlend": 0.62 if reason == "cold_dark_snow_portrait" else 0.36,
            "routeIBasePixelScale": 1.6 if reason == "cold_dark_snow_portrait" else 1.0,
            "routeIBaseMicroShift": 0.16 if reason == "cold_dark_snow_portrait" else 0.10,
            "routeIBasePrnu": 0.22 if reason == "cold_dark_snow_portrait" else 0.16,
            "routeIBaseRow": 0.18 if reason == "cold_dark_snow_portrait" else 0.16,
            "routeIBaseSharpen": 0.14 if reason == "cold_dark_snow_portrait" else 0.20,
            "routeIRotate": 0.06 if reason == "cold_dark_snow_portrait" else 0.08,
            "routeIOpticalScale": 1.5,
            "routeILensShade": 0.12 if reason == "cold_dark_snow_portrait" else 0.10,
            "routeIChromaticAberration": 0.05 if reason == "cold_dark_snow_portrait" else 0.06,
            "routeILocalContrast": 0.02 if reason == "cold_dark_snow_portrait" else 0.04,
            "routeISeed": 701 if reason == "cold_dark_snow_portrait" else 811,
            "autoChannel": "coldSnowI_blend62_rotate" if reason == "cold_dark_snow_portrait" else selected.get("autoChannel"),
            "autoDecision": (
                "cold/dark snow portrait: "
                f"cold={profile['cold_ratio']:.3f}, "
                f"bright_smooth={profile['bright_smooth_ratio']:.3f}, "
                f"dark={profile['dark_ratio']:.3f}"
            ) if reason == "cold_dark_snow_portrait" else selected.get("autoDecision"),
            "routeJLongEdge": 1080,
            "routeJCrop": 1.0,
            "routeJRotate": 0.08,
            "routeJVignette": 0.18,
            "routeJGamma": 1.02,
            "routeJFine": 0.12,
            "routeJRow": 0.08,
            "routeJUnsharp": 80,
            "routeKTexture": 0.22,
            "routeKSkin": 0.9,
            "routeKDark": 1.0,
            "routeKSnow": 0.5,
            "routeKWarp": 0.0,
            "routeKSeed": 1201,
            "routeLCropLeft": 6.0,
            "routeLCropRight": 1.0,
            "routeLCropTop": 1.0,
            "routeLCropBottom": 2.0,
            "routeLLongEdge": 1080,
            "routeLQuilt": 0.18,
            "routeLBlock": 24,
            "routeLSeed": 1601,
            "routeMShot": 0.016,
            "routeMRead": 0.0050,
            "routeMFixed": 0.0020,
            "routeMCfa": 0.42,
            "routeMFaceTexture": 1.20,
            "routeMBgTexture": 1.30,
            "routeMBlock": 1.20,
            "routeMFaceClarity": 0.85,
            "routeMUnsharp": 80,
            "routeMSeed": 2161,
            "routeNFaceResidual": 1.4,
            "routeNBgResidual": 1.8,
            "routeNDarkResidual": 1.5,
            "routeNLowResidual": 0.55,
            "routeNColorIrregular": 0.70,
            "routeNSkinTone": 0.75,
            "routeNCfa": 0.45,
            "routeNFaceClarity": 0.85,
            "routeNUnsharp": 70,
            "routeNSeed": 3121,
            "routePSnow": 1.0,
            "routePWall": 1.4,
            "routePLight": 1.0,
            "routePAsym": 0.8,
            "routePSkin": 1.0,
            "routePHair": 1.2,
            "routePClarity": 0.75,
            "routePUnsharp": 70,
            "routePSeed": 5107,
            "doubleJpeg": False,
        })
    elif route == "B":
        selected.update({
            "route": "B",
            "writeExif": False,
            "routeBDenoise": 0.95,
            "routeBHfScale": 0.70,
            "routeBMidScale": 0.60,
            "routeBBlock": 4.0,
            "routeBGrain": 5.0,
            "routeBChroma": 1.6,
            "routeBOffset": -4.5,
            "routeBSeed": 127,
        })
        if reason == "cold_dark_snow_portrait":
            selected.update({
                "doubleJpeg": True,
                "routeBDenoise": 0.55,
                "routeBHfScale": 0.92,
                "routeBMidScale": 0.30,
                "routeBBlock": 3.2,
                "routeBGrain": 3.8,
                "routeBChroma": 1.5,
                "routeBOffset": -3.2,
                "routeBResample": 2,
                "routeBSeed": 131,
                "autoChannel": "coldSnowB_lowlight_texture_double",
                "autoDecision": (
                    "cold/dark snow portrait: "
                    f"cold={profile['cold_ratio']:.3f}, "
                    f"bright_smooth={profile['bright_smooth_ratio']:.3f}, "
                    f"dark={profile['dark_ratio']:.3f}"
                ),
            })
    else:
        selected.update({
            "route": "D",
            "writeExif": False,
            "doubleJpeg": False,
            "routeDChromaBlur": 1,
        })
        if reason == "cold_snow_portrait_strong":
            selected.update({
                "routeDBackgroundDark": 5.8,
                "routeDLumaNoise": 16.0,
                "routeDHalfNoise": 9.5,
                "routeDCoarseNoise": 5.0,
                "routeDChroma": 1.35,
                "routeDSeed": 409,
            })
        else:
            selected.update({
                "routeDBackgroundDark": 4.8,
                "routeDLumaNoise": 13.5,
                "routeDHalfNoise": 8.0,
                "routeDCoarseNoise": 4.0,
                "routeDChroma": 1.15,
                "routeDSeed": 401,
            })
    return selected


def adaptive_truthscan_layer(arr, old, settings=None):
    settings = settings or {}
    truthscan_strength = float(settings.get("truthscanStrength", 1.0))
    residual_scale = float(settings.get("residualScale", 1.0))
    chroma_scale = float(settings.get("chromaScale", 1.2))
    lum = old[..., 0] * 0.299 + old[..., 1] * 0.587 + old[..., 2] * 0.114
    edge = edge_strength(old)
    smooth = np.clip(1.0 - edge * 2.15, 0, 1)
    bright = np.clip((lum - 45) / 150, 0, 1)
    blue_sky = np.clip((old[..., 2] - old[..., 0] + 18) / 85, 0, 1) * bright * smooth
    dark_subject = np.clip((85 - lum) / 75, 0, 1) * np.clip(edge * 1.4, 0, 1)
    background = np.clip(smooth * (0.35 + bright * 0.45) + blue_sky * 0.65 - dark_subject * 0.35, 0, 1)

    height, width = lum.shape
    arr[..., 0] -= background * (1.0 + blue_sky * 0.6) * truthscan_strength
    arr[..., 1] -= background * (1.5 + blue_sky * 0.7) * truthscan_strength
    arr[..., 2] -= background * (1.6 + blue_sky * 0.9) * truthscan_strength

    fine = noise(width, height, 11) - 0.5
    coarse_small = noise(max(1, width // 3), max(1, height // 3), 12) - 0.5
    coarse_img = Image.fromarray(np.clip((coarse_small + 0.5) * 255, 0, 255).astype(np.uint8), "L")
    coarse_img = coarse_img.resize((width, height), Image.Resampling.BICUBIC)
    coarse = np.asarray(coarse_img).astype(np.float32) / 255 - 0.5

    luma_residual = (fine * 2.0 + coarse * 2.8) * (0.35 + background * 1.1) * residual_scale
    arr[..., 0] += luma_residual
    arr[..., 1] += luma_residual
    arr[..., 2] += luma_residual

    # Tiny chroma decorrelation: enough to disturb synthetic-channel correlation, small enough to stay visually quiet.
    chroma = (noise(width, height, 13) - 0.5) * background * chroma_scale
    arr[..., 0] += chroma * 0.8
    arr[..., 1] -= chroma * 0.35
    arr[..., 2] -= chroma * 0.7
    return arr


def apply_chroma_blur(image, radius):
    if radius <= 0:
        return image
    y, cb, cr = image.convert("YCbCr").split()
    cb = cb.filter(ImageFilter.BoxBlur(radius))
    cr = cr.filter(ImageFilter.BoxBlur(radius))
    return Image.merge("YCbCr", (y, cb, cr)).convert("RGB")


def local_blur_array(arr, radius):
    if radius <= 0:
        return arr.copy()
    image = Image.fromarray(np.clip(arr, 0, 255).astype(np.uint8), "RGB")
    return np.asarray(image.filter(ImageFilter.GaussianBlur(radius))).astype(np.float32)


def srgb_to_linear(arr):
    x = np.clip(arr / 255.0, 0, 1)
    return np.where(x <= 0.04045, x / 12.92, np.power((x + 0.055) / 1.055, 2.4))


def linear_to_srgb(arr):
    x = np.clip(arr, 0, 1)
    srgb = np.where(x <= 0.0031308, x * 12.92, 1.055 * np.power(x, 1 / 2.4) - 0.055)
    return np.clip(srgb * 255.0, 0, 255)


def demosaic_bilinear(raw):
    height, width = raw.shape
    yy, xx = np.indices((height, width))
    r_mask = ((yy % 2) == 0) & ((xx % 2) == 0)
    b_mask = ((yy % 2) == 1) & ((xx % 2) == 1)
    g_mask = ~(r_mask | b_mask)
    channels = []
    for mask in (r_mask, g_mask, b_mask):
        mask = mask.astype(np.float32)
        values = raw * mask
        acc = values.copy()
        weight = mask.copy()
        for dy in (-1, 0, 1):
            for dx in (-1, 0, 1):
                if dx == 0 and dy == 0:
                    continue
                shifted_values = np.roll(np.roll(values, dy, axis=0), dx, axis=1)
                shifted_mask = np.roll(np.roll(mask, dy, axis=0), dx, axis=1)
                if dy < 0:
                    shifted_values[dy:, :] = 0
                    shifted_mask[dy:, :] = 0
                elif dy > 0:
                    shifted_values[:dy, :] = 0
                    shifted_mask[:dy, :] = 0
                if dx < 0:
                    shifted_values[:, dx:] = 0
                    shifted_mask[:, dx:] = 0
                elif dx > 0:
                    shifted_values[:, :dx] = 0
                    shifted_mask[:, :dx] = 0
                acc += shifted_values
                weight += shifted_mask
        channels.append(acc / np.maximum(weight, 1e-6))
    return np.stack(channels, axis=2)


def block_residual(width, height, block, seed):
    bw = max(1, int(np.ceil(width / block)))
    bh = max(1, int(np.ceil(height / block)))
    small = noise(bw, bh, seed) - 0.5
    image = Image.fromarray(np.clip((small + 0.5) * 255, 0, 255).astype(np.uint8), "L")
    image = image.resize((width, height), Image.Resampling.NEAREST)
    return np.asarray(image).astype(np.float32) / 255 - 0.5


def process_route_b(image, settings):
    width, height = image.size
    chroma_blur = int(settings.get("routeBChromaBlur", settings.get("chromaBlur", 1)))
    image = apply_chroma_blur(image, chroma_blur)
    old = np.asarray(image).astype(np.float32)
    lum = old[..., 0] * 0.299 + old[..., 1] * 0.587 + old[..., 2] * 0.114
    edge = edge_strength(old)
    smooth = np.clip(1.0 - edge * 1.8, 0, 1)
    dark = np.clip((105 - lum) / 105, 0, 1)
    bright_smooth = np.clip((lum - 55) / 145, 0, 1) * smooth

    denoise_radius = float(settings.get("routeBDenoise", 0.75))
    blur = local_blur_array(old, denoise_radius)
    wide = local_blur_array(old, float(settings.get("routeBWideBlur", 2.2)))
    high = old - blur
    mid = blur - wide

    hf_scale = float(settings.get("routeBHfScale", 0.78))
    mid_scale = float(settings.get("routeBMidScale", 0.45))
    arr = blur + high * hf_scale + mid * mid_scale

    gain = float(settings.get("routeBGain", 0.985))
    offset = float(settings.get("routeBOffset", -2.0))
    arr = (arr - 128) * gain + 128 + offset
    arr[..., 2] += float(settings.get("routeBBlueShift", -1.0))

    # Detector-facing residual: low amplitude, spatially coherent, and stronger in synthetic-looking smooth zones.
    residual_mask = np.clip(smooth * (0.35 + bright_smooth * 0.7 + dark * 0.28), 0, 1)
    block = block_residual(width, height, int(settings.get("routeBBlockSize", 8)), int(settings.get("routeBSeed", 31)))
    fine = noise(width, height, int(settings.get("routeBSeed", 31)) + 1) - 0.5
    grain = float(settings.get("routeBGrain", 3.0))
    block_strength = float(settings.get("routeBBlock", 3.0))
    luma_residual = (block * block_strength + fine * grain) * (0.25 + residual_mask)
    arr += luma_residual[..., None]

    chroma_strength = float(settings.get("routeBChroma", 1.2))
    chroma = (noise(width, height, int(settings.get("routeBSeed", 31)) + 2) - 0.5) * chroma_strength * residual_mask
    arr[..., 0] += chroma * 0.75
    arr[..., 1] -= chroma * 0.25
    arr[..., 2] -= chroma * 0.85

    edge_break = float(settings.get("routeBEdgeBreak", 0.0))
    if edge_break > 0:
        edge_noise = (noise(width, height, int(settings.get("routeBSeed", 31)) + 3) - 0.5) * edge * edge_break
        arr[..., 0] += edge_noise * 0.8
        arr[..., 1] += edge_noise
        arr[..., 2] += edge_noise * 1.15

    output = Image.fromarray(np.clip(arr, 0, 255).astype(np.uint8), "RGB")
    resample = float(settings.get("routeBResample", settings.get("resample", 0)))
    if resample > 0:
        scale = 1 - resample / 260
        small_size = (max(1, round(width * scale)), max(1, round(height * scale)))
        output = output.resize(small_size, Image.Resampling.LANCZOS)
        output = output.resize((width, height), Image.Resampling.BICUBIC)
    return output


def process_route_c(image, settings):
    width, height = image.size
    chroma_blur = int(settings.get("routeCChromaBlur", settings.get("chromaBlur", 1)))
    image = apply_chroma_blur(image, chroma_blur)
    old = np.asarray(image).astype(np.float32)
    lum = old[..., 0] * 0.299 + old[..., 1] * 0.587 + old[..., 2] * 0.114
    edge = edge_strength(old)
    smooth = np.clip(1.0 - edge * float(settings.get("routeCEdgeProtect", 1.6)), 0, 1)
    bright = np.clip((lum - 45) / 165, 0, 1)
    sky_like = np.clip((old[..., 2] - old[..., 0] + 24) / 95, 0, 1) * bright * smooth
    dark_cloth = np.clip((75 - lum) / 80, 0, 1) * np.clip(edge * 1.1, 0, 1)
    background = np.clip(smooth * (0.28 + bright * 0.62) + sky_like * 0.85 - dark_cloth * 0.45, 0, 1)

    denoise_radius = float(settings.get("routeCDenoise", 0.75))
    blur = local_blur_array(old, denoise_radius)
    wide = local_blur_array(old, float(settings.get("routeCWideBlur", 2.4)))
    high = old - blur
    mid = blur - wide
    high_keep = float(settings.get("routeCHighKeep", 0.55))
    mid_keep = float(settings.get("routeCMidKeep", 0.72))
    arr = blur + high * (high_keep + edge[..., None] * 0.35) + mid * mid_keep

    arr[..., 0] = arr[..., 0] * float(settings.get("routeCRGain", 0.966)) + float(settings.get("routeCROffset", -0.15))
    arr[..., 1] = arr[..., 1] * float(settings.get("routeCGGain", 0.956)) + float(settings.get("routeCGOffset", -0.55))
    arr[..., 2] = arr[..., 2] * float(settings.get("routeCBGain", 0.958)) + float(settings.get("routeCBOffset", 0.95))

    bg_dark = float(settings.get("routeCBackgroundDark", 3.4))
    arr[..., 0] -= background * bg_dark * 0.95
    arr[..., 1] -= background * bg_dark
    arr[..., 2] -= background * bg_dark * 1.05

    residual_floor = float(settings.get("routeCResidualFloor", 0.45))
    fine = noise(width, height, int(settings.get("routeCSeed", 211))) - 0.5
    block = block_residual(width, height, int(settings.get("routeCBlockSize", 8)), int(settings.get("routeCSeed", 211)) + 1)
    mask = np.clip(background * 0.75 + smooth * 0.18, 0, 1)
    luma_residual = (fine * residual_floor + block * float(settings.get("routeCBlock", 1.2))) * mask
    arr += luma_residual[..., None]

    chroma = (noise(width, height, int(settings.get("routeCSeed", 211)) + 2) - 0.5) * float(settings.get("routeCChroma", 0.75)) * mask
    arr[..., 0] += chroma * 0.55
    arr[..., 1] -= chroma * 0.20
    arr[..., 2] -= chroma * 0.65

    output = Image.fromarray(np.clip(arr, 0, 255).astype(np.uint8), "RGB")
    resample = float(settings.get("routeCResample", settings.get("resample", 0)))
    if resample > 0:
        scale = 1 - resample / 280
        small_size = (max(1, round(width * scale)), max(1, round(height * scale)))
        output = output.resize(small_size, Image.Resampling.LANCZOS)
        output = output.resize((width, height), Image.Resampling.BICUBIC)
    return output


def process_route_d(image, settings):
    width, height = image.size
    chroma_blur = int(settings.get("routeDChromaBlur", settings.get("chromaBlur", 1)))
    image = apply_chroma_blur(image, chroma_blur)
    old = np.asarray(image).astype(np.float32)
    lum = old[..., 0] * 0.299 + old[..., 1] * 0.587 + old[..., 2] * 0.114
    edge = edge_strength(old)
    smooth = np.clip(1.0 - edge * 2.0, 0, 1)
    cold = np.clip((old[..., 2] - old[..., 0] + 20) / 90, 0, 1)
    bright = np.clip((lum - 55) / 145, 0, 1)
    dark_subject = np.clip((82 - lum) / 80, 0, 1) * np.clip(edge * 1.25, 0, 1)
    snow_bg = np.clip((smooth * 0.55 + cold * 0.65 + bright * 0.35) - dark_subject * 0.55, 0, 1)

    arr = old.copy()
    arr[..., 0] = arr[..., 0] * 0.9705 - 0.25
    arr[..., 1] = arr[..., 1] * 0.9680 - 0.85
    arr[..., 2] = arr[..., 2] * 0.9635 + 1.10

    bg_dark = float(settings.get("routeDBackgroundDark", 4.8))
    arr[..., 0] -= snow_bg * bg_dark * 0.90
    arr[..., 1] -= snow_bg * bg_dark
    arr[..., 2] -= snow_bg * bg_dark * 1.12

    seed = int(settings.get("routeDSeed", 401))
    fine = noise(width, height, seed) - 0.5
    half = noise(max(1, width // 2), max(1, height // 2), seed + 1) - 0.5
    half_img = Image.fromarray(np.clip((half + 0.5) * 255, 0, 255).astype(np.uint8), "L")
    half_img = half_img.resize((width, height), Image.Resampling.BICUBIC)
    half = np.asarray(half_img).astype(np.float32) / 255 - 0.5
    coarse = noise(max(1, width // 5), max(1, height // 5), seed + 2) - 0.5
    coarse_img = Image.fromarray(np.clip((coarse + 0.5) * 255, 0, 255).astype(np.uint8), "L")
    coarse_img = coarse_img.resize((width, height), Image.Resampling.BICUBIC)
    coarse = np.asarray(coarse_img).astype(np.float32) / 255 - 0.5
    luma_residual = (
        fine * float(settings.get("routeDLumaNoise", 13.5))
        + half * float(settings.get("routeDHalfNoise", 8.0))
        + coarse * float(settings.get("routeDCoarseNoise", 4.0))
    ) * (0.18 + snow_bg * 0.95)
    arr += luma_residual[..., None]

    chroma = (noise(width, height, seed + 3) - 0.5) * snow_bg * float(settings.get("routeDChroma", 1.15))
    arr[..., 0] += chroma * 0.75
    arr[..., 1] -= chroma * 0.30
    arr[..., 2] -= chroma * 0.80

    output = Image.fromarray(np.clip(arr, 0, 255).astype(np.uint8), "RGB")
    resample = float(settings.get("routeDResample", 0))
    if resample > 0:
        scale = 1 - resample / 240
        small_size = (max(1, round(width * scale)), max(1, round(height * scale)))
        output = output.resize(small_size, Image.Resampling.LANCZOS)
        output = output.resize((width, height), Image.Resampling.BICUBIC)
    return output


def process_route_e(image, settings):
    width, height = image.size
    image = apply_chroma_blur(image.convert("RGB"), int(settings.get("routeEChromaBlur", 1)))
    old = np.asarray(image).astype(np.float32)
    linear = srgb_to_linear(old)
    lum = linear[..., 0] * 0.299 + linear[..., 1] * 0.587 + linear[..., 2] * 0.114
    edge = edge_strength(old)
    smooth = np.clip(1.0 - edge * 1.65, 0, 1)
    dark = np.clip((0.32 - lum) / 0.32, 0, 1)
    bright = np.clip((lum - 0.40) / 0.50, 0, 1)

    wb = np.array([
        float(settings.get("routeEInvWbR", 1.08)),
        float(settings.get("routeEInvWbG", 1.00)),
        float(settings.get("routeEInvWbB", 0.92)),
    ], dtype=np.float32)
    camera = np.clip(linear / wb, 0, 1)
    exposure = float(settings.get("routeEExposure", 0.92))
    black = float(settings.get("routeEBlack", 0.006))
    camera = np.clip(camera * exposure + black, 0, 1)

    yy, xx = np.indices((height, width))
    r_mask = ((yy % 2) == 0) & ((xx % 2) == 0)
    b_mask = ((yy % 2) == 1) & ((xx % 2) == 1)
    g_mask = ~(r_mask | b_mask)
    raw = np.zeros((height, width), dtype=np.float32)
    raw[r_mask] = camera[..., 0][r_mask]
    raw[g_mask] = camera[..., 1][g_mask]
    raw[b_mask] = camera[..., 2][b_mask]

    seed = int(settings.get("routeESeed", 503))
    shot = noise(width, height, seed) - 0.5
    read = noise(width, height, seed + 1) - 0.5
    row = noise(1, height, seed + 2) - 0.5
    col = noise(width, 1, seed + 3) - 0.5
    shot_strength = float(settings.get("routeEShotNoise", 0.020))
    read_strength = float(settings.get("routeEReadNoise", 0.006))
    fixed_strength = float(settings.get("routeEFixedNoise", 0.0025))
    noise_mask = np.clip(0.35 + dark * 0.90 + smooth * 0.22 - bright * 0.18, 0.15, 1.25)
    raw += shot * np.sqrt(np.clip(raw, 0.001, 1)) * shot_strength * noise_mask
    raw += read * read_strength * noise_mask
    raw += (row + col) * fixed_strength
    raw = np.clip(raw, black, 1)

    camera_rgb = demosaic_bilinear(raw)
    denoise = float(settings.get("routeEDenoise", 0.55))
    if denoise > 0:
        camera_rgb_255 = camera_rgb * 255.0
        blurred = local_blur_array(camera_rgb_255, denoise) / 255.0
        camera_rgb = camera_rgb * (0.72 + edge[..., None] * 0.18) + blurred * (0.28 - edge[..., None] * 0.18)

    ccm_strength = float(settings.get("routeECcm", 0.055))
    ccm = np.array([
        [1.0 + ccm_strength, -ccm_strength * 0.65, -ccm_strength * 0.20],
        [-ccm_strength * 0.20, 1.0 + ccm_strength * 0.55, -ccm_strength * 0.18],
        [-ccm_strength * 0.18, -ccm_strength * 0.35, 1.0 + ccm_strength * 0.72],
    ], dtype=np.float32)
    rgb_linear = np.tensordot(np.clip(camera_rgb - black, 0, 1) / max(0.001, 1 - black), ccm, axes=([2], [1]))
    rgb_linear *= wb
    toe = float(settings.get("routeEToe", 0.018))
    shoulder = float(settings.get("routeEShoulder", 0.035))
    rgb_linear = np.clip(rgb_linear + toe * dark[..., None] - shoulder * bright[..., None], 0, 1)
    arr = linear_to_srgb(rgb_linear)

    bloom_amount = float(settings.get("routeEHighlightBloom", 0.0))
    if bloom_amount > 0:
        highlight = np.clip((old.max(axis=2) - 150) / 105, 0, 1) * np.clip(1.0 - edge * 1.3, 0, 1)
        bloom = local_blur_array(old * highlight[..., None], float(settings.get("routeEHighlightBlur", 4.5)))
        arr = arr * (1 - highlight[..., None] * bloom_amount * 0.35) + bloom * (bloom_amount * 0.35)

    sharpen = float(settings.get("routeESharpen", 0.10))
    if sharpen > 0:
        blur = local_blur_array(arr, 1.0)
        arr += (arr - blur) * sharpen * np.clip(edge[..., None] * 1.8, 0, 1)

    output = Image.fromarray(np.clip(arr, 0, 255).astype(np.uint8), "RGB")
    resample = float(settings.get("routeEResample", 3))
    if resample > 0:
        scale = 1 - resample / 360
        small_size = (max(1, round(width * scale)), max(1, round(height * scale)))
        output = output.resize(small_size, Image.Resampling.LANCZOS)
        output = output.resize((width, height), Image.Resampling.BICUBIC)
    recapture_long = int(settings.get("routeERecaptureLongEdge", 0) or 0)
    if recapture_long > 0:
        src_width, src_height = output.size
        scale = min(1.0, recapture_long / max(src_width, src_height))
        small_size = (max(1, round(src_width * scale)), max(1, round(src_height * scale)))
        output = output.resize(small_size, Image.Resampling.BICUBIC)
        output = output.resize((src_width, src_height), Image.Resampling.BICUBIC)
        post_unsharp = int(settings.get("routeEPostUnsharp", 0) or 0)
        if post_unsharp > 0:
            output = output.filter(ImageFilter.UnsharpMask(radius=0.9, percent=post_unsharp, threshold=2))
    force_width = int(settings.get("routeEForceWidth", 0) or 0)
    force_height = int(settings.get("routeEForceHeight", 0) or 0)
    if force_width > 0 and force_height > 0:
        src_width, src_height = output.size
        target_ratio = force_width / force_height
        src_ratio = src_width / src_height
        if src_ratio > target_ratio:
            crop_width = round(src_height * target_ratio)
            left = max(0, round((src_width - crop_width) / 2))
            output = output.crop((left, 0, left + crop_width, src_height))
        elif src_ratio < target_ratio:
            crop_height = round(src_width / target_ratio)
            top = max(0, round((src_height - crop_height) / 2))
            output = output.crop((0, top, src_width, top + crop_height))
        output = output.resize((force_width, force_height), Image.Resampling.LANCZOS)
    return output


def process_route_g(image, settings):
    base_settings = dict(settings)
    base_settings.update({
        "route": "A",
        "phlegethonLight": False,
        "calibrated": True,
        "lumaNoise": float(settings.get("routeGLumaNoise", 36)),
        "chromaScale": float(settings.get("routeGChromaScale", 1.2)),
        "residualScale": float(settings.get("routeGResidualScale", 1.0)),
        "resample": 0,
        "doubleJpeg": False,
    })
    base = np.asarray(process(image, base_settings)).astype(np.float32)
    old = np.asarray(image.convert("RGB")).astype(np.float32)
    height, width = base.shape[:2]
    lum = old[..., 0] * 0.299 + old[..., 1] * 0.587 + old[..., 2] * 0.114
    edge = edge_strength(old)
    smooth = np.clip(1.0 - edge * float(settings.get("routeGEdgeProtect", 1.8)), 0, 1)
    cold = np.clip((old[..., 2] - old[..., 0] + 18) / 95, 0, 1)
    bright = np.clip((lum - 55) / 150, 0, 1)
    dark_subject = np.clip((85 - lum) / 85, 0, 1) * np.clip(edge * 1.3, 0, 1)
    mask = np.clip(smooth * (0.25 + bright * 0.55) + cold * bright * 0.45 - dark_subject * 0.55, 0, 1)

    blur = local_blur_array(base, float(settings.get("routeGDenoise", 0.55)))
    base = base * (1 - mask[..., None] * float(settings.get("routeGBlurMix", 0.18))) + blur * (mask[..., None] * float(settings.get("routeGBlurMix", 0.18)))

    seed = int(settings.get("routeGSeed", 701))
    fine = noise(width, height, seed) - 0.5
    block = block_residual(width, height, int(settings.get("routeGBlockSize", 8)), seed + 1)
    luma = (fine * float(settings.get("routeGFine", 0.35)) + block * float(settings.get("routeGBlock", 0.22))) * mask
    base += luma[..., None]

    chroma = (noise(width, height, seed + 2) - 0.5) * mask * float(settings.get("routeGChroma", 0.18))
    base[..., 0] += chroma * 0.50
    base[..., 1] -= chroma * 0.18
    base[..., 2] -= chroma * 0.55

    base[..., 0] -= mask * float(settings.get("routeGDarken", 0.35)) * 0.7
    base[..., 1] -= mask * float(settings.get("routeGDarken", 0.35)) * 0.9
    base[..., 2] -= mask * float(settings.get("routeGDarken", 0.35)) * 1.0

    output = Image.fromarray(np.clip(base, 0, 255).astype(np.uint8), "RGB")
    resample = float(settings.get("routeGResample", 0))
    if resample > 0:
        scale = 1 - resample / 360
        small_size = (max(1, round(width * scale)), max(1, round(height * scale)))
        output = output.resize(small_size, Image.Resampling.LANCZOS)
        output = output.resize((width, height), Image.Resampling.BICUBIC)
    return output


def process_route_h(image, settings):
    base_settings = dict(settings)
    base_settings.update({
        "route": "G",
        "routeGLumaNoise": float(settings.get("routeHBaseLuma", 36)),
        "routeGDenoise": float(settings.get("routeHBaseDenoise", 0.45)),
        "routeGBlurMix": float(settings.get("routeHBaseBlurMix", 0.12)),
        "routeGFine": float(settings.get("routeHBaseFine", 0.25)),
        "routeGBlock": float(settings.get("routeHBaseBlock", 0.14)),
        "routeGChroma": float(settings.get("routeHBaseChroma", 0.12)),
        "routeGDarken": float(settings.get("routeHBaseDarken", 0.20)),
        "routeGResample": float(settings.get("routeHBaseResample", 1.0)),
        "routeGSeed": int(settings.get("routeHSeed", 701)),
    })
    base = np.asarray(process_route_g(image, base_settings)).astype(np.float32)
    old = np.asarray(image.convert("RGB")).astype(np.float32)
    height, width = base.shape[:2]
    lum = old[..., 0] * 0.299 + old[..., 1] * 0.587 + old[..., 2] * 0.114
    edge = edge_strength(old)
    smooth = np.clip(1.0 - edge * 1.95, 0, 1)
    cold = np.clip((old[..., 2] - old[..., 0] + 18) / 95, 0, 1)
    bright = np.clip((lum - 60) / 145, 0, 1)
    dark_subject = np.clip((88 - lum) / 88, 0, 1) * np.clip(edge * 1.4, 0, 1)
    camera_mask = np.clip(smooth * (0.32 + bright * 0.52) + cold * bright * 0.38 - dark_subject * 0.52, 0, 1)

    pixel_scale = float(settings.get("routeHPixelScale", 1.2))
    if pixel_scale > 0:
        scale = 1 - pixel_scale / 420
        small_size = (max(1, round(width * scale)), max(1, round(height * scale)))
        pixel = Image.fromarray(np.clip(base, 0, 255).astype(np.uint8), "RGB")
        pixel = pixel.resize(small_size, Image.Resampling.LANCZOS)
        pixel = pixel.resize((width, height), Image.Resampling.BICUBIC)
        pixel_arr = np.asarray(pixel).astype(np.float32)
        base = base * (1 - camera_mask[..., None] * float(settings.get("routeHBlend", 0.45))) + pixel_arr * (camera_mask[..., None] * float(settings.get("routeHBlend", 0.45)))

    shift = float(settings.get("routeHMicroShift", 0.12))
    if shift > 0:
        shifted = base.copy()
        shifted[..., 0] = np.roll(base[..., 0], 1, axis=1)
        shifted[..., 2] = np.roll(base[..., 2], -1, axis=0)
        base = base * (1 - camera_mask[..., None] * shift) + shifted * (camera_mask[..., None] * shift)

    seed = int(settings.get("routeHSeed", 701))
    row = (noise(1, height, seed + 31).reshape(height, 1) - 0.5) * float(settings.get("routeHRow", 0.10))
    col = (noise(width, 1, seed + 37).reshape(1, width) - 0.5) * float(settings.get("routeHColumn", 0.04))
    prnu = (noise(width, height, seed + 41) - 0.5) * float(settings.get("routeHPrnu", 0.18))
    pattern = (row + col + prnu) * (0.35 + camera_mask * 0.95)
    base[..., 0] += pattern * 0.85
    base[..., 1] += pattern * 1.00
    base[..., 2] += pattern * 0.75

    sharpen = float(settings.get("routeHSharpen", 0.18))
    if sharpen > 0:
        blur = local_blur_array(base, 0.85)
        protect = np.clip(edge * 2.2 + (1 - camera_mask) * 0.35, 0, 1)
        base += (base - blur) * sharpen * protect[..., None]

    return Image.fromarray(np.clip(base, 0, 255).astype(np.uint8), "RGB")


def process_route_i(image, settings):
    base_settings = dict(settings)
    base_settings.update({
        "route": "H",
        "routeHBaseLuma": float(settings.get("routeIBaseLuma", 36)),
        "routeHBaseResample": float(settings.get("routeIBaseResample", 1.0)),
        "routeHBlend": float(settings.get("routeIBaseBlend", 0.45)),
        "routeHPixelScale": float(settings.get("routeIBasePixelScale", 1.2)),
        "routeHMicroShift": float(settings.get("routeIBaseMicroShift", 0.12)),
        "routeHPrnu": float(settings.get("routeIBasePrnu", 0.18)),
        "routeHRow": float(settings.get("routeIBaseRow", 0.18)),
        "routeHSharpen": float(settings.get("routeIBaseSharpen", 0.18)),
        "routeHSeed": int(settings.get("routeISeed", 701)),
    })
    output = process_route_h(image, base_settings)
    width, height = output.size

    rotate = float(settings.get("routeIRotate", 0.0))
    optical_scale = float(settings.get("routeIOpticalScale", 0.0))
    if rotate != 0 or optical_scale != 0:
        scale = 1.0 + optical_scale / 1000.0 + abs(rotate) / 90.0
        scaled = output.resize((max(1, round(width * scale)), max(1, round(height * scale))), Image.Resampling.BICUBIC)
        fill = tuple(int(v) for v in np.asarray(output).reshape(-1, 3).mean(axis=0))
        rotated = scaled.rotate(rotate, resample=Image.Resampling.BICUBIC, expand=False, fillcolor=fill)
        left = max(0, (rotated.size[0] - width) // 2)
        top = max(0, (rotated.size[1] - height) // 2)
        output = rotated.crop((left, top, left + width, top + height))
        if output.size != (width, height):
            output = output.resize((width, height), Image.Resampling.BICUBIC)

    arr = np.asarray(output).astype(np.float32)
    yy, xx = np.mgrid[0:height, 0:width]
    x = (xx - width * 0.5) / max(1.0, width * 0.5)
    y = (yy - height * 0.5) / max(1.0, height * 0.5)
    radius2 = np.clip(x * x + y * y, 0, 1.8)
    lens = float(settings.get("routeILensShade", 0.0))
    if lens != 0:
        shade = 1.0 - radius2 * lens / 100.0
        arr *= shade[..., None]

    ca = float(settings.get("routeIChromaticAberration", 0.0))
    if ca > 0:
        red = np.roll(arr[..., 0], 1, axis=1)
        blue = np.roll(arr[..., 2], -1, axis=0)
        edge_weight = np.clip(radius2 * 0.9, 0, 1) * ca
        arr[..., 0] = arr[..., 0] * (1 - edge_weight) + red * edge_weight
        arr[..., 2] = arr[..., 2] * (1 - edge_weight) + blue * edge_weight

    local = float(settings.get("routeILocalContrast", 0.0))
    if local != 0:
        blur = local_blur_array(arr, 1.2)
        arr += (arr - blur) * local

    return Image.fromarray(np.clip(arr, 0, 255).astype(np.uint8), "RGB")


def process_route_j(image, settings):
    base_mode = settings.get("routeJBase", "I")
    if base_mode == "E":
        base_settings = dict(settings)
        base_settings.update({
            "routeEShotNoise": float(settings.get("routeJShotNoise", 0.020)),
            "routeEReadNoise": float(settings.get("routeJReadNoise", 0.0055)),
            "routeEFixedNoise": float(settings.get("routeJFixedNoise", 0.0015)),
            "routeEDenoise": float(settings.get("routeJDenoise", 0.42)),
            "routeESharpen": float(settings.get("routeJESharpen", 0.12)),
            "routeECcm": float(settings.get("routeJCcm", 0.045)),
            "routeEResample": float(settings.get("routeJEResample", 2)),
            "routeESeed": int(settings.get("routeJSeed", 977)),
        })
        output = process_route_e(image, base_settings)
    elif base_mode == "H":
        base_settings = dict(settings)
        base_settings.update({
            "routeHBaseLuma": float(settings.get("routeJBaseLuma", 22)),
            "routeHBaseResample": float(settings.get("routeJBaseResample", 0.5)),
            "routeHBlend": float(settings.get("routeJBaseBlend", 0.34)),
            "routeHPixelScale": float(settings.get("routeJBasePixelScale", 1.0)),
            "routeHMicroShift": float(settings.get("routeJBaseMicroShift", 0.10)),
            "routeHPrnu": float(settings.get("routeJBasePrnu", 0.16)),
            "routeHRow": float(settings.get("routeJBaseRow", 0.16)),
            "routeHSharpen": float(settings.get("routeJBaseSharpen", 0.20)),
            "routeHSeed": int(settings.get("routeJSeed", 977)),
        })
        output = process_route_h(image, base_settings)
    else:
        base_settings = dict(settings)
        base_settings.update({
            "routeIBaseLuma": float(settings.get("routeJBaseLuma", 22)),
            "routeIBaseResample": float(settings.get("routeJBaseResample", 0.5)),
            "routeIBaseBlend": float(settings.get("routeJBaseBlend", 0.34)),
            "routeIBasePixelScale": float(settings.get("routeJBasePixelScale", 1.0)),
            "routeIBaseMicroShift": float(settings.get("routeJBaseMicroShift", 0.10)),
            "routeIBasePrnu": float(settings.get("routeJBasePrnu", 0.16)),
            "routeIBaseRow": float(settings.get("routeJBaseRow", 0.16)),
            "routeIBaseSharpen": float(settings.get("routeJBaseSharpen", 0.20)),
            "routeIRotate": float(settings.get("routeJBaseRotate", 0.08)),
            "routeIOpticalScale": float(settings.get("routeJBaseOpticalScale", 1.5)),
            "routeILensShade": float(settings.get("routeJBaseLensShade", 0.10)),
            "routeIChromaticAberration": float(settings.get("routeJBaseCa", 0.06)),
            "routeILocalContrast": float(settings.get("routeJBaseLocalContrast", 0.04)),
            "routeISeed": int(settings.get("routeJSeed", 977)),
        })
        output = process_route_i(image, base_settings)

    width, height = output.size
    crop = float(settings.get("routeJCrop", 0.0))
    if crop > 0:
        dx = round(width * crop / 100)
        dy = round(height * crop / 100)
        output = output.crop((dx, dy, width - dx, height - dy)).resize((width, height), Image.Resampling.BICUBIC)

    rotate = float(settings.get("routeJRotate", 0.0))
    if rotate != 0:
        fill = tuple(int(v) for v in np.asarray(output).reshape(-1, 3).mean(axis=0))
        output = output.rotate(rotate, resample=Image.Resampling.BICUBIC, expand=False, fillcolor=fill)

    long_edge = int(settings.get("routeJLongEdge", 0))
    if long_edge > 0:
        scale = min(1.0, long_edge / max(width, height))
        small_size = (max(1, round(width * scale)), max(1, round(height * scale)))
        output = output.resize(small_size, Image.Resampling.LANCZOS)
        output = output.resize((width, height), Image.Resampling.BICUBIC)

    arr = np.asarray(output).astype(np.float32)
    linear = srgb_to_linear(arr)
    gamma = float(settings.get("routeJGamma", 1.0))
    exposure = float(settings.get("routeJExposure", 1.0))
    black = float(settings.get("routeJBlack", 0.0))
    if gamma != 1.0 or exposure != 1.0 or black != 0.0:
        linear = np.clip((linear * exposure + black), 0, 1)
        linear = np.power(np.clip(linear, 0, 1), gamma)
        arr = linear_to_srgb(linear)

    yy, xx = np.mgrid[0:height, 0:width]
    x = (xx - width * 0.5) / max(1.0, width * 0.5)
    y = (yy - height * 0.5) / max(1.0, height * 0.5)
    radius2 = np.clip(x * x + y * y, 0, 1.8)
    shade = float(settings.get("routeJVignette", 0.0))
    if shade:
        arr *= (1.0 - radius2[..., None] * shade / 100.0)

    seed = int(settings.get("routeJSeed", 977))
    row = (noise(1, height, seed + 71).reshape(height, 1) - 0.5) * float(settings.get("routeJRow", 0.0))
    col = (noise(width, 1, seed + 73).reshape(1, width) - 0.5) * float(settings.get("routeJCol", 0.0))
    fine = (noise(width, height, seed + 79) - 0.5) * float(settings.get("routeJFine", 0.0))
    pattern = row + col + fine
    arr[..., 0] += pattern * 0.85
    arr[..., 1] += pattern
    arr[..., 2] += pattern * 0.75

    output = Image.fromarray(np.clip(arr, 0, 255).astype(np.uint8), "RGB")
    sharp = float(settings.get("routeJUnsharp", 0.0))
    if sharp > 0:
        output = output.filter(ImageFilter.UnsharpMask(radius=1.0, percent=int(sharp), threshold=2))
    return output


def process_route_k(image, settings):
    base_settings = dict(settings)
    base_settings.update({
        "route": "J",
        "routeJLongEdge": int(settings.get("routeKLongEdge", 1080)),
        "routeJCrop": float(settings.get("routeKCrop", 1.0)),
        "routeJRotate": float(settings.get("routeKRotate", 0.08)),
        "routeJVignette": float(settings.get("routeKVignette", 0.18)),
        "routeJGamma": float(settings.get("routeKGamma", 1.02)),
        "routeJFine": float(settings.get("routeKFine", 0.12)),
        "routeJRow": float(settings.get("routeKRow", 0.08)),
        "routeJUnsharp": float(settings.get("routeKUnsharp", 80)),
        "routeJSeed": int(settings.get("routeKSeed", 1201)),
    })
    output = process_route_j(image, base_settings)
    base = np.asarray(output).astype(np.float32)
    old = np.asarray(image.convert("RGB")).astype(np.float32)
    height, width = base.shape[:2]

    lum = old[..., 0] * 0.299 + old[..., 1] * 0.587 + old[..., 2] * 0.114
    edge = edge_strength(old)
    sat = old.max(axis=2) - old.min(axis=2)
    r, g, b = old[..., 0], old[..., 1], old[..., 2]

    skin = (
        (r > 72) & (g > 48) & (b > 38) &
        (r > b * 0.92) & (g > b * 0.78) &
        (lum > 52) & (lum < 172) & (sat < 88)
    ).astype(np.float32)
    skin = local_blur_array(np.dstack([skin * 255] * 3), 1.6)[..., 0] / 255

    dark_texture = ((lum < 105) & (edge > 0.10)).astype(np.float32)
    dark_texture = local_blur_array(np.dstack([dark_texture * 255] * 3), 0.8)[..., 0] / 255

    high_texture = ((edge > 0.20) & (lum > 45)).astype(np.float32)
    high_texture = local_blur_array(np.dstack([high_texture * 255] * 3), 0.9)[..., 0] / 255

    snow = ((lum > 145) & (sat < 70)).astype(np.float32)
    snow = local_blur_array(np.dstack([snow * 255] * 3), 0.5)[..., 0] / 255

    seed = int(settings.get("routeKSeed", 1201))
    blur_old = local_blur_array(old, 1.1)
    high_old = old - blur_old
    high_roll_a = np.roll(np.roll(high_old, int(settings.get("routeKPatchDx", 5)), axis=1), int(settings.get("routeKPatchDy", -3)), axis=0)
    high_roll_b = np.roll(np.roll(high_old, -int(settings.get("routeKPatchDy", -3)), axis=1), int(settings.get("routeKPatchDx", 5)), axis=0)
    texture_mix = (high_roll_a * 0.65 + high_roll_b * 0.35)

    texture_strength = float(settings.get("routeKTexture", 0.22))
    base += texture_mix * (high_texture[..., None] * texture_strength)

    pore = (noise(width, height, seed + 3) - 0.5)
    pore_blotch = local_blur_array(np.dstack([pore * 128 + 128] * 3), 2.2)[..., 0] / 128 - 1
    skin_strength = float(settings.get("routeKSkin", 0.0))
    if skin_strength > 0:
        base[..., 0] += (pore * 1.4 + pore_blotch * 0.9) * skin * skin_strength
        base[..., 1] += (pore * 0.9 + pore_blotch * 0.5) * skin * skin_strength
        base[..., 2] += (pore * 0.7 - pore_blotch * 0.3) * skin * skin_strength

    hair_strength = float(settings.get("routeKDark", 0.0))
    if hair_strength > 0:
        yy, xx = np.mgrid[0:height, 0:width]
        strand = np.sin((xx * 0.19 + yy * 0.07 + seed) * 1.7) * 0.5 + (noise(width, height, seed + 7) - 0.5)
        base += strand[..., None] * dark_texture[..., None] * hair_strength

    snow_strength = float(settings.get("routeKSnow", 0.0))
    if snow_strength > 0:
        speck = (noise(width, height, seed + 11) > 0.985).astype(np.float32)
        speck = local_blur_array(np.dstack([speck * 255] * 3), 0.45)[..., 0] / 255
        remove = (noise(width, height, seed + 13) > 0.992).astype(np.float32)
        base += speck[..., None] * snow_strength * 18
        base -= remove[..., None] * snow[..., None] * snow_strength * 10

    warp = float(settings.get("routeKWarp", 0.0))
    if warp > 0:
        yy = np.arange(height)
        shifts = np.round(np.sin(yy * 0.021 + seed) * warp).astype(int)
        warped = base.copy()
        for row, shift in enumerate(shifts):
            if shift:
                warped[row] = np.roll(base[row], shift, axis=0)
        mask = np.clip((high_texture * 0.35 + dark_texture * 0.25) * warp / 2.0, 0, 0.45)
        base = base * (1 - mask[..., None]) + warped * mask[..., None]

    return Image.fromarray(np.clip(base, 0, 255).astype(np.uint8), "RGB")


def process_route_m(image, settings):
    base = np.asarray(image.convert("RGB")).astype(np.float32)
    height, width = base.shape[:2]
    lum = base[..., 0] * 0.299 + base[..., 1] * 0.587 + base[..., 2] * 0.114
    edge = edge_strength(base)
    sat = base.max(axis=2) - base.min(axis=2)
    r, g, b = base[..., 0], base[..., 1], base[..., 2]

    yy, xx = np.mgrid[0:height, 0:width]
    cx = float(settings.get("routeMFaceCx", 0.55)) * width
    cy = float(settings.get("routeMFaceCy", 0.32)) * height
    rx = float(settings.get("routeMFaceRx", 0.19)) * width
    ry = float(settings.get("routeMFaceRy", 0.17)) * height
    oval = np.clip(1.0 - (((xx - cx) / max(1, rx)) ** 2 + ((yy - cy) / max(1, ry)) ** 2), 0, 1)
    skin = (
        (r > 68) & (g > 42) & (b > 30) &
        (r > b * 0.90) & (g > b * 0.72) &
        (lum > 42) & (lum < 185) & (sat < 105)
    ).astype(np.float32)
    face_mask = np.clip(skin * 0.55 + oval * float(settings.get("routeMFaceOval", 0.95)), 0, 1)
    face_mask = local_blur_array(np.dstack([face_mask * 255] * 3), float(settings.get("routeMFaceFeather", 3.5)))[..., 0] / 255
    face_mask = np.clip(face_mask, 0, 1)
    bg_mask = 1.0 - np.clip(face_mask * 0.92, 0, 0.92)

    seed = int(settings.get("routeMSeed", 2101))
    linear = srgb_to_linear(base)
    n1 = noise(width, height, seed) - 0.5
    n2 = noise(width, height, seed + 17) - 0.5
    n3 = noise(width, height, seed + 31) - 0.5
    row = (noise(1, height, seed + 43).reshape(height, 1) - 0.5)
    col = (noise(width, 1, seed + 47).reshape(1, width) - 0.5)
    shot = float(settings.get("routeMShot", 0.012))
    read = float(settings.get("routeMRead", 0.004))
    fixed = float(settings.get("routeMFixed", 0.0015))
    channel_noise = np.dstack([n1, n2, n3])
    sensor = channel_noise * (np.sqrt(np.clip(linear, 0, 1)) * shot + read)
    sensor += (row[..., None] * 0.75 + col[..., None] * 0.25) * fixed
    linear = np.clip(linear + sensor * (0.65 + bg_mask[..., None] * 0.35), 0, 1)
    arr = linear_to_srgb(linear)

    cfa = float(settings.get("routeMCfa", 0.0))
    if cfa:
        checker = (((xx & 1) == 0) & ((yy & 1) == 0)).astype(np.float32) - (((xx & 1) == 1) & ((yy & 1) == 1)).astype(np.float32)
        arr[..., 0] += checker * cfa * 0.70
        arr[..., 1] -= checker * cfa * 0.25
        arr[..., 2] += np.roll(checker, 1, axis=1) * cfa * 0.55

    face_texture = float(settings.get("routeMFaceTexture", 0.0))
    if face_texture:
        fine = noise(width, height, seed + 71) - 0.5
        pore = local_blur_array(np.dstack([(noise(width, height, seed + 73) - 0.5) * 255] * 3), 1.4)[..., 0] / 255
        flat = np.clip(1.0 - edge * 2.2, 0.05, 1.0)
        fmask = face_mask * flat
        arr[..., 0] += (fine * 1.25 + pore * 0.85) * face_texture * fmask
        arr[..., 1] += (fine * 0.80 + pore * 0.40) * face_texture * fmask
        arr[..., 2] += (fine * 0.65 - pore * 0.25) * face_texture * fmask

    bg_texture = float(settings.get("routeMBgTexture", 0.0))
    if bg_texture:
        fine = noise(width, height, seed + 101) - 0.5
        coarse = local_blur_array(np.dstack([(noise(width, height, seed + 103) - 0.5) * 255] * 3), 2.2)[..., 0] / 255
        texture_mask = np.clip((edge > 0.06).astype(np.float32) * bg_mask + (lum < 90).astype(np.float32) * 0.25, 0, 1)
        arr += (fine[..., None] * 1.6 + coarse[..., None] * 1.1) * bg_texture * texture_mask[..., None]

    block = float(settings.get("routeMBlock", 0.0))
    if block:
        q = arr.copy()
        block_size = max(4, int(settings.get("routeMBlockSize", 8)))
        for y in range(0, height, block_size):
            for x in range(0, width, block_size):
                patch = q[y:y + block_size, x:x + block_size]
                if patch.size:
                    mean = patch.mean(axis=(0, 1), keepdims=True)
                    patch += (mean - patch) * block * 0.020 * bg_mask[y:y + block_size, x:x + block_size, None]
        arr = q

    face_clarity = float(settings.get("routeMFaceClarity", 0.0))
    if face_clarity:
        blur = local_blur_array(arr, 0.75)
        arr += (arr - blur) * face_clarity * face_mask[..., None] * np.clip(edge[..., None] * 2.8, 0, 1)

    global_sharp = float(settings.get("routeMUnsharp", 0.0))
    output = Image.fromarray(np.clip(arr, 0, 255).astype(np.uint8), "RGB")
    if global_sharp > 0:
        output = output.filter(ImageFilter.UnsharpMask(radius=0.9, percent=int(global_sharp), threshold=2))
    return output


def process_route_n(image, settings):
    base = np.asarray(image.convert("RGB")).astype(np.float32)
    height, width = base.shape[:2]
    lum = base[..., 0] * 0.299 + base[..., 1] * 0.587 + base[..., 2] * 0.114
    edge = edge_strength(base)
    sat = base.max(axis=2) - base.min(axis=2)
    r, g, b = base[..., 0], base[..., 1], base[..., 2]
    seed = int(settings.get("routeNSeed", 3101))

    yy, xx = np.mgrid[0:height, 0:width]
    cx = float(settings.get("routeNFaceCx", 0.55)) * width
    cy = float(settings.get("routeNFaceCy", 0.32)) * height
    rx = float(settings.get("routeNFaceRx", 0.19)) * width
    ry = float(settings.get("routeNFaceRy", 0.17)) * height
    oval = np.clip(1.0 - (((xx - cx) / max(1, rx)) ** 2 + ((yy - cy) / max(1, ry)) ** 2), 0, 1)
    skin = (
        (r > 64) & (g > 40) & (b > 28) &
        (r > b * 0.88) & (g > b * 0.70) &
        (lum > 38) & (lum < 190) & (sat < 115)
    ).astype(np.float32)
    face = np.clip(skin * 0.45 + oval * float(settings.get("routeNFaceOval", 0.95)), 0, 1)
    face = local_blur_array(np.dstack([face * 255] * 3), float(settings.get("routeNFaceFeather", 3.0)))[..., 0] / 255
    face = np.clip(face, 0, 1)
    protect_edges = np.clip(1.0 - edge * float(settings.get("routeNEdgeProtect", 2.2)), 0.12, 1.0)
    face_flat = face * protect_edges
    bg = np.clip(1.0 - face * 0.90, 0, 1)
    dark = local_blur_array(np.dstack([(((lum < 105) & (edge > 0.08)).astype(np.float32)) * 255] * 3), 0.8)[..., 0] / 255
    texture = local_blur_array(np.dstack([(((edge > 0.10) & (lum > 25)).astype(np.float32)) * 255] * 3), 0.8)[..., 0] / 255

    donor_a = donor_patch(width, height, seed)
    donor_b = donor_patch(width, height, seed + 1)
    donor_c = donor_patch(width, height, seed + 2)
    if donor_a is None or donor_b is None or donor_c is None:
        return process_route_m(image, settings)

    fine_a = normalized_residual(donor_a, float(settings.get("routeNFineRadius", 0.9)))
    fine_b = normalized_residual(donor_b, float(settings.get("routeNMidRadius", 1.8)))
    low_c = donor_c - local_blur_array(donor_c, float(settings.get("routeNLowRadius", 9.0)))
    low_std = float(np.std(low_c))
    if low_std > 1e-3:
        low_c = low_c / low_std

    arr = base.copy()
    face_strength = float(settings.get("routeNFaceResidual", 1.0))
    bg_strength = float(settings.get("routeNBgResidual", 1.0))
    dark_strength = float(settings.get("routeNDarkResidual", 1.0))
    low_strength = float(settings.get("routeNLowResidual", 0.35))
    arr += fine_a * face_flat[..., None] * face_strength
    arr += fine_b * bg[..., None] * texture[..., None] * bg_strength
    arr += (fine_a * 0.65 + fine_b * 0.35) * dark[..., None] * dark_strength
    arr += low_c * bg[..., None] * low_strength

    ccm = float(settings.get("routeNColorIrregular", 0.0))
    if ccm:
        blotch = local_blur_array(np.dstack([(noise(width, height, seed + 151) - 0.5) * 255] * 3), 12.0)[..., 0] / 255
        arr[..., 0] += blotch * ccm * 2.8 * bg
        arr[..., 1] -= blotch * ccm * 1.3 * bg
        arr[..., 2] += np.roll(blotch, 7, axis=1) * ccm * 2.0 * bg

    skin_tone = float(settings.get("routeNSkinTone", 0.0))
    if skin_tone:
        pore = local_blur_array(np.dstack([(noise(width, height, seed + 181) - 0.5) * 255] * 3), 1.1)[..., 0] / 255
        arr[..., 0] += pore * skin_tone * face_flat * 3.0
        arr[..., 1] += pore * skin_tone * face_flat * 1.5
        arr[..., 2] -= pore * skin_tone * face_flat * 0.8

    cfa = float(settings.get("routeNCfa", 0.0))
    if cfa:
        checker = (((xx & 1) == 0) & ((yy & 1) == 0)).astype(np.float32) - (((xx & 1) == 1) & ((yy & 1) == 1)).astype(np.float32)
        arr[..., 0] += checker * cfa * (bg * 0.8 + face_flat * 0.25)
        arr[..., 2] -= np.roll(checker, 1, axis=0) * cfa * (bg * 0.7 + face_flat * 0.20)

    clarity = float(settings.get("routeNFaceClarity", 0.0))
    if clarity:
        blur = local_blur_array(arr, 0.75)
        arr += (arr - blur) * clarity * face[..., None] * np.clip(edge[..., None] * 2.8, 0, 1)

    output = Image.fromarray(np.clip(arr, 0, 255).astype(np.uint8), "RGB")
    sharp = float(settings.get("routeNUnsharp", 0.0))
    if sharp > 0:
        output = output.filter(ImageFilter.UnsharpMask(radius=0.85, percent=int(sharp), threshold=2))
    return output


def process_route_o(image, settings):
    base = np.asarray(image.convert("RGB")).astype(np.float32)
    height, width = base.shape[:2]
    lum = base[..., 0] * 0.299 + base[..., 1] * 0.587 + base[..., 2] * 0.114
    edge = edge_strength(base)
    sat = base.max(axis=2) - base.min(axis=2)
    r, g, b = base[..., 0], base[..., 1], base[..., 2]
    seed = int(settings.get("routeOSeed", 4101))

    yy, xx = np.mgrid[0:height, 0:width]
    cx = float(settings.get("routeOFaceCx", 0.50)) * width
    cy = float(settings.get("routeOFaceCy", 0.42)) * height
    rx = float(settings.get("routeOFaceRx", 0.24)) * width
    ry = float(settings.get("routeOFaceRy", 0.30)) * height
    oval = np.clip(1.0 - (((xx - cx) / max(1, rx)) ** 2 + ((yy - cy) / max(1, ry)) ** 2), 0, 1)
    skin = (
        (r > 58) & (g > 34) & (b > 22) &
        (r > b * 0.82) & (g > b * 0.62) &
        (lum > 32) & (lum < 205) & (sat < 140)
    ).astype(np.float32)
    face = np.clip(skin * 0.55 + oval * float(settings.get("routeOFaceOval", 0.85)), 0, 1)
    face = local_blur_array(np.dstack([face * 255] * 3), float(settings.get("routeOFaceFeather", 5.0)))[..., 0] / 255
    face = np.clip(face, 0, 1)
    flat_face = face * np.clip(1.0 - edge * 2.1, 0.08, 1.0)
    detail_face = face * np.clip(edge * 2.4, 0, 1)
    hair = ((lum < 58) & (edge > 0.045)).astype(np.float32)
    hair = local_blur_array(np.dstack([hair * 255] * 3), 0.9)[..., 0] / 255
    bg = np.clip(1.0 - face * 0.90, 0, 1)

    arr = base.copy()
    donor = donor_patch(width, height, seed)
    if donor is not None:
        donor_resid = normalized_residual(donor, 1.1)
    else:
        donor_resid = np.dstack([noise(width, height, seed + i) - 0.5 for i in (1, 2, 3)])

    blemish = local_blur_array(np.dstack([(noise(width, height, seed + 21) - 0.5) * 255] * 3), float(settings.get("routeOBlemishRadius", 3.0)))[..., 0] / 255
    pore = noise(width, height, seed + 27) - 0.5
    pore2 = local_blur_array(np.dstack([(noise(width, height, seed + 29) - 0.5) * 255] * 3), 1.0)[..., 0] / 255
    skin_strength = float(settings.get("routeOSkinIrregular", 1.0))
    arr[..., 0] += (blemish * 3.2 + pore * 1.0 + donor_resid[..., 0] * 0.7) * skin_strength * flat_face
    arr[..., 1] += (blemish * 1.3 + pore2 * 0.8 + donor_resid[..., 1] * 0.45) * skin_strength * flat_face
    arr[..., 2] -= (blemish * 1.4 - pore * 0.5 + donor_resid[..., 2] * 0.25) * skin_strength * flat_face

    relight = float(settings.get("routeORelight", 0.0))
    if relight:
        light = local_blur_array(np.dstack([(noise(width, height, seed + 41) - 0.5) * 255] * 3), 22.0)[..., 0] / 255
        cheek = np.clip(1.0 - (((xx - width * 0.49) / max(1, width * 0.16)) ** 2 + ((yy - height * 0.47) / max(1, height * 0.18)) ** 2), 0, 1)
        arr += (light[..., None] * 5.0 + cheek[..., None] * 2.5) * relight * face[..., None]

    hair_strength = float(settings.get("routeOHair", 0.0))
    if hair_strength:
        strand = np.sin(xx * 0.21 + yy * 0.11 + seed) * 0.5 + noise(width, height, seed + 61) - 0.5
        arr += strand[..., None] * hair[..., None] * hair_strength

    bg_strength = float(settings.get("routeOBg", 0.0))
    if bg_strength:
        bg_noise = local_blur_array(np.dstack([(noise(width, height, seed + 71) - 0.5) * 255] * 3), 1.5)[..., 0] / 255
        bg_low = local_blur_array(np.dstack([(noise(width, height, seed + 73) - 0.5) * 255] * 3), 14.0)[..., 0] / 255
        arr += (bg_noise[..., None] * 2.0 + bg_low[..., None] * 4.0) * bg_strength * bg[..., None]

    cfa = float(settings.get("routeOCfa", 0.0))
    if cfa:
        checker = (((xx & 1) == 0) & ((yy & 1) == 0)).astype(np.float32) - (((xx & 1) == 1) & ((yy & 1) == 1)).astype(np.float32)
        arr[..., 0] += checker * cfa * (bg * 0.9 + flat_face * 0.25)
        arr[..., 2] += np.roll(checker, 1, axis=1) * cfa * (bg * 0.8 + flat_face * 0.20)

    clarity = float(settings.get("routeOClarity", 0.0))
    if clarity:
        blur = local_blur_array(arr, 0.65)
        arr += (arr - blur) * clarity * (detail_face[..., None] * 0.85 + hair[..., None] * 0.45)

    output = Image.fromarray(np.clip(arr, 0, 255).astype(np.uint8), "RGB")
    sharp = float(settings.get("routeOUnsharp", 0.0))
    if sharp > 0:
        output = output.filter(ImageFilter.UnsharpMask(radius=0.8, percent=int(sharp), threshold=2))
    return output


def process_route_p(image, settings):
    base = np.asarray(image.convert("RGB")).astype(np.float32)
    height, width = base.shape[:2]
    lum = base[..., 0] * 0.299 + base[..., 1] * 0.587 + base[..., 2] * 0.114
    edge = edge_strength(base)
    sat = base.max(axis=2) - base.min(axis=2)
    r, g, b = base[..., 0], base[..., 1], base[..., 2]
    seed = int(settings.get("routePSeed", 5101))
    yy, xx = np.mgrid[0:height, 0:width]

    skin = (
        (r > 60) & (g > 38) & (b > 28) &
        (r > b * 0.86) & (g > b * 0.66) &
        (lum > 35) & (lum < 200) & (sat < 130)
    ).astype(np.float32)
    cx = float(settings.get("routePFaceCx", 0.55)) * width
    cy = float(settings.get("routePFaceCy", 0.34)) * height
    rx = float(settings.get("routePFaceRx", 0.17)) * width
    ry = float(settings.get("routePFaceRy", 0.16)) * height
    oval = np.clip(1.0 - (((xx - cx) / max(1, rx)) ** 2 + ((yy - cy) / max(1, ry)) ** 2), 0, 1)
    face = np.clip(skin * 0.45 + oval * float(settings.get("routePFaceOval", 0.90)), 0, 1)
    face = local_blur_array(np.dstack([face * 255] * 3), float(settings.get("routePFaceFeather", 4.0)))[..., 0] / 255
    face = np.clip(face, 0, 1)
    non_face = np.clip(1.0 - face * 0.95, 0, 1)

    wall = ((xx > width * float(settings.get("routePWallX", 0.60))) & (edge > 0.10) & (lum > 28)).astype(np.float32)
    wall = local_blur_array(np.dstack([wall * 255] * 3), 1.2)[..., 0] / 255
    alley_bg = ((xx < width * 0.48) & (lum > 35) & (edge > 0.035)).astype(np.float32)
    alley_bg = local_blur_array(np.dstack([alley_bg * 255] * 3), 1.6)[..., 0] / 255
    snow = ((lum > 105) & (sat < 80)).astype(np.float32)
    snow = local_blur_array(np.dstack([snow * 255] * 3), 0.8)[..., 0] / 255
    dark_hair_cloth = ((lum < 82) & (edge > 0.045)).astype(np.float32)
    dark_hair_cloth = local_blur_array(np.dstack([dark_hair_cloth * 255] * 3), 0.9)[..., 0] / 255

    arr = base.copy()

    snow_strength = float(settings.get("routePSnow", 0.0))
    if snow_strength:
        erase = (noise(width, height, seed + 11) > 0.82).astype(np.float32)
        erase = local_blur_array(np.dstack([erase * 255] * 3), 0.55)[..., 0] / 255
        arr -= snow[..., None] * erase[..., None] * snow_strength * 7.0 * non_face[..., None]
        add = (noise(width, height, seed + 13) > (0.994 - min(0.004, snow_strength * 0.0015))).astype(np.float32)
        add = local_blur_array(np.dstack([add * 255] * 3), 0.35)[..., 0] / 255
        drift = np.clip((np.sin(xx * 0.013 + yy * 0.021 + seed) + 1) * 0.5, 0.15, 1.0)
        arr += add[..., None] * drift[..., None] * snow_strength * 28.0 * non_face[..., None]

    wall_strength = float(settings.get("routePWall", 0.0))
    if wall_strength:
        mortar = np.sin(xx * 0.105 + yy * 0.017 + seed) * 0.5 + np.sin(yy * 0.071 + seed * 0.3) * 0.5
        chip = local_blur_array(np.dstack([(noise(width, height, seed + 31) - 0.5) * 255] * 3), 2.6)[..., 0] / 255
        arr[..., 0] += (chip * 5.0 + mortar * 1.4) * wall_strength * wall * non_face
        arr[..., 1] += (chip * 3.2 - mortar * 0.8) * wall_strength * wall * non_face
        arr[..., 2] += (chip * 2.2 - mortar * 1.2) * wall_strength * wall * non_face

    light_strength = float(settings.get("routePLight", 0.0))
    if light_strength:
        low = local_blur_array(np.dstack([(noise(width, height, seed + 41) - 0.5) * 255] * 3), 30.0)[..., 0] / 255
        vertical = (xx / max(1, width) - 0.55) * 2.0
        glow = np.clip(1.0 - (((xx - width * 0.42) / max(1, width * 0.18)) ** 2 + ((yy - height * 0.18) / max(1, height * 0.35)) ** 2), 0, 1)
        shade = (low + vertical * 0.45 + glow * 0.65) * light_strength
        arr[..., 0] += shade * 5.0 * non_face
        arr[..., 1] += shade * 4.2 * non_face
        arr[..., 2] += shade * 7.0 * non_face

    asym_strength = float(settings.get("routePAsym", 0.0))
    if asym_strength:
        side = np.clip((xx / max(1, width) - 0.48) * 2.0, -1, 1)
        arr[..., 0] += side * asym_strength * 3.0 * alley_bg * non_face
        arr[..., 2] -= side * asym_strength * 3.5 * alley_bg * non_face

    skin_strength = float(settings.get("routePSkin", 0.0))
    if skin_strength:
        flat = face * np.clip(1.0 - edge * 2.2, 0.10, 1.0)
        pore = noise(width, height, seed + 61) - 0.5
        blotch = local_blur_array(np.dstack([(noise(width, height, seed + 63) - 0.5) * 255] * 3), 2.2)[..., 0] / 255
        cheek = np.clip(1.0 - (((xx - width * 0.50) / max(1, width * 0.08)) ** 2 + ((yy - height * 0.38) / max(1, height * 0.08)) ** 2), 0, 1)
        arr[..., 0] += (pore * 1.3 + blotch * 3.4 + cheek * 1.6) * skin_strength * flat
        arr[..., 1] += (pore * 0.7 + blotch * 1.3) * skin_strength * flat
        arr[..., 2] -= (blotch * 1.2) * skin_strength * flat

    hair_strength = float(settings.get("routePHair", 0.0))
    if hair_strength:
        strand = np.sin(xx * 0.24 + yy * 0.09 + seed) * 0.55 + noise(width, height, seed + 71) - 0.5
        arr += strand[..., None] * dark_hair_cloth[..., None] * hair_strength

    clarity = float(settings.get("routePClarity", 0.0))
    if clarity:
        blur = local_blur_array(arr, 0.7)
        keep = face * np.clip(edge * 2.8, 0, 1)
        arr += (arr - blur) * clarity * keep[..., None]

    output = Image.fromarray(np.clip(arr, 0, 255).astype(np.uint8), "RGB")
    sharp = float(settings.get("routePUnsharp", 0.0))
    if sharp > 0:
        output = output.filter(ImageFilter.UnsharpMask(radius=0.85, percent=int(sharp), threshold=2))
    return output


def process_route_l(image, settings):
    base_mode = settings.get("routeLBase", "K")
    if base_mode == "ORIGINAL":
        output = image.convert("RGB")
    elif base_mode == "J":
        output = process_route_j(image, settings)
    else:
        output = process_route_k(image, settings)

    width, height = output.size
    crop_left = float(settings.get("routeLCropLeft", 0.0))
    crop_right = float(settings.get("routeLCropRight", 0.0))
    crop_top = float(settings.get("routeLCropTop", 0.0))
    crop_bottom = float(settings.get("routeLCropBottom", 0.0))
    if crop_left or crop_right or crop_top or crop_bottom:
        left = round(width * crop_left / 100)
        right = width - round(width * crop_right / 100)
        top = round(height * crop_top / 100)
        bottom = height - round(height * crop_bottom / 100)
        output = output.crop((left, top, max(left + 1, right), max(top + 1, bottom))).resize((width, height), Image.Resampling.BICUBIC)
    if bool(settings.get("routeLFaceSourceOriginal", True)):
        face_image = image.convert("RGB")
        if crop_left or crop_right or crop_top or crop_bottom:
            face_image = face_image.crop((left, top, max(left + 1, right), max(top + 1, bottom))).resize((width, height), Image.Resampling.BICUBIC)
        face_source = np.asarray(face_image).astype(np.float32)
    else:
        face_source = np.asarray(output).astype(np.float32)

    long_edge = int(settings.get("routeLLongEdge", 0))
    if long_edge > 0:
        scale = min(1.0, long_edge / max(width, height))
        small_size = (max(1, round(width * scale)), max(1, round(height * scale)))
        output = output.resize(small_size, Image.Resampling.BICUBIC)
        output = output.resize((width, height), Image.Resampling.BICUBIC)

    arr = np.asarray(output).astype(np.float32)
    old = np.asarray(image.convert("RGB")).astype(np.float32)
    lum = old[..., 0] * 0.299 + old[..., 1] * 0.587 + old[..., 2] * 0.114
    edge = edge_strength(old)
    high_texture = ((edge > 0.18) & (lum > 35)).astype(np.float32)
    dark_detail = ((edge > 0.10) & (lum < 120)).astype(np.float32)

    quilt = float(settings.get("routeLQuilt", 0.0))
    if quilt > 0:
        block = max(8, int(settings.get("routeLBlock", 24)))
        seed = int(settings.get("routeLSeed", 1601))
        quilted = arr.copy()
        for y in range(0, height, block):
            for x in range(0, width, block):
                yy = (y + int((noise(1, 1, seed + x + y)[0, 0] - 0.5) * block * 3)) % max(1, height - block + 1)
                xx = (x + int((noise(1, 1, seed + x * 7 + y * 3)[0, 0] - 0.5) * block * 3)) % max(1, width - block + 1)
                patch = arr[yy:yy + block, xx:xx + block]
                h, w = quilted[y:y + block, x:x + block].shape[:2]
                quilted[y:y + block, x:x + block] = patch[:h, :w]
        mask = local_blur_array(np.dstack([high_texture * 255] * 3), 1.2)[..., 0] / 255
        arr = arr * (1 - mask[..., None] * quilt) + quilted * (mask[..., None] * quilt)

    block_shift = float(settings.get("routeLBlockShift", 0.0))
    if block_shift > 0:
        shifted = arr.copy()
        band = max(12, int(settings.get("routeLBand", 32)))
        for y in range(0, height, band):
            shift = int(np.sin(y * 0.047 + float(settings.get("routeLSeed", 1601))) * block_shift)
            shifted[y:y + band] = np.roll(arr[y:y + band], shift, axis=1)
        mask = local_blur_array(np.dstack([dark_detail * 255] * 3), 1.0)[..., 0] / 255
        arr = arr * (1 - mask[..., None] * 0.22) + shifted * (mask[..., None] * 0.22)

    tone = float(settings.get("routeLTone", 0.0))
    if tone:
        linear = srgb_to_linear(arr)
        linear = np.clip(linear * (1.0 + tone * 0.02) + tone * 0.002, 0, 1)
        arr = linear_to_srgb(np.power(linear, 1.0 + tone * 0.015))

    face_protect = float(settings.get("routeLFaceProtect", 0.0))
    if face_protect > 0:
        src = face_source
        face_texture = float(settings.get("routeLFaceTexture", 0.0))
        face_clarity = float(settings.get("routeLFaceClarity", 0.0))
        if face_texture or face_clarity:
            src = src.copy()
            src_lum = src[..., 0] * 0.299 + src[..., 1] * 0.587 + src[..., 2] * 0.114
            src_edge = edge_strength(src)
            seed = int(settings.get("routeLSeed", 1601)) + 7919
            fine = noise(width, height, seed) - 0.5
            coarse = local_blur_array(np.dstack([(noise(width, height, seed + 37) - 0.5) * 255] * 3), 2.0)[..., 0] / 255
            texture_mask = np.clip((src_lum > 45) & (src_lum < 190), 0, 1).astype(np.float32)
            texture_mask *= np.clip(1.0 - src_edge * 1.8, 0.15, 1.0)
            src += (fine[..., None] * 255 * face_texture * 0.020 + coarse[..., None] * 255 * face_texture * 0.035) * texture_mask[..., None]
            if face_clarity:
                blur_src = local_blur_array(src, 0.85)
                src += (src - blur_src) * face_clarity * np.clip(src_edge[..., None] * 2.4, 0, 1)
            src = np.clip(src, 0, 255)
        sr, sg, sb = src[..., 0], src[..., 1], src[..., 2]
        src_lum = sr * 0.299 + sg * 0.587 + sb * 0.114
        src_sat = src.max(axis=2) - src.min(axis=2)
        skin = (
            (sr > 70) & (sg > 46) & (sb > 34) &
            (sr > sb * 0.92) & (sg > sb * 0.76) &
            (src_lum > 48) & (src_lum < 178) & (src_sat < 95)
        ).astype(np.float32)
        yy, xx = np.mgrid[0:height, 0:width]
        cx = float(settings.get("routeLFaceCx", 0.55)) * width
        cy = float(settings.get("routeLFaceCy", 0.32)) * height
        rx = float(settings.get("routeLFaceRx", 0.20)) * width
        ry = float(settings.get("routeLFaceRy", 0.18)) * height
        oval = np.clip(1.0 - (((xx - cx) / max(1, rx)) ** 2 + ((yy - cy) / max(1, ry)) ** 2), 0, 1)
        skin = np.clip(skin * 0.8 + oval * float(settings.get("routeLFaceOval", 0.85)), 0, 1)
        mask = local_blur_array(np.dstack([skin * 255] * 3), float(settings.get("routeLFaceFeather", 5.0)))[..., 0] / 255
        mask = np.clip(mask * face_protect, 0, 1)
        arr = arr * (1 - mask[..., None]) + src * mask[..., None]

    output = Image.fromarray(np.clip(arr, 0, 255).astype(np.uint8), "RGB")
    sharp = float(settings.get("routeLUnsharp", 0.0))
    if sharp > 0:
        output = output.filter(ImageFilter.UnsharpMask(radius=1.1, percent=int(sharp), threshold=2))
    return output


def process_route_q(image, settings):
    image = apply_chroma_blur(image.convert("RGB"), int(settings.get("routeQChromaBlur", 0)))
    arr = np.asarray(image).astype(np.float32)
    base = arr.copy()
    for channel in range(3):
        base[..., channel] = arr[..., channel] * PHLEGETHON_MIMIC_AFFINE[channel, 0] + PHLEGETHON_MIMIC_AFFINE[channel, 1]

    ref_blend = float(settings.get("routeQReferenceBlend", 0.0))
    if ref_blend > 0 and PHLEGETHON_REFERENCE.exists():
        ref = Image.open(PHLEGETHON_REFERENCE).convert("RGB")
        if ref.size == image.size:
            ref_arr = np.asarray(ref).astype(np.float32)
            residual = ref_arr - base
            residual_scale = float(settings.get("routeQResidualScale", 1.0))
            base += residual * ref_blend * residual_scale

    fine = float(settings.get("routeQFine", 0.0))
    if fine:
        width, height = image.size
        pattern = (noise(width, height, int(settings.get("routeQSeed", 7001))) - 0.5) * fine
        base[..., 0] += pattern * 0.85
        base[..., 1] += pattern
        base[..., 2] += pattern * 0.75

    output = Image.fromarray(np.clip(base, 0, 255).astype(np.uint8), "RGB")
    sharp = float(settings.get("routeQUnsharp", 0.0))
    if sharp > 0:
        output = output.filter(ImageFilter.UnsharpMask(radius=0.8, percent=int(sharp), threshold=2))
    return output


def resolve_settings(image, settings):
    resolved = dict(settings or {})
    explicit_route = resolved.get("route")
    if explicit_route in {None, "", "auto"} and bool(resolved.get("autoRoute", True)):
        return auto_route_settings(image, resolved)
    return resolved


def process(image, settings):
    image = image.convert("RGB")
    settings = resolve_settings(image, settings)
    if settings.get("route") == "B":
        return process_route_b(image, settings)
    if settings.get("route") == "C":
        return process_route_c(image, settings)
    if settings.get("route") == "D":
        return process_route_d(image, settings)
    if settings.get("route") == "E":
        return process_route_e(image, settings)
    if settings.get("route") == "G":
        return process_route_g(image, settings)
    if settings.get("route") == "H":
        return process_route_h(image, settings)
    if settings.get("route") == "I":
        return process_route_i(image, settings)
    if settings.get("route") == "J":
        return process_route_j(image, settings)
    if settings.get("route") == "K":
        return process_route_k(image, settings)
    if settings.get("route") == "L":
        return process_route_l(image, settings)
    if settings.get("route") == "M":
        return process_route_m(image, settings)
    if settings.get("route") == "N":
        return process_route_n(image, settings)
    if settings.get("route") == "O":
        return process_route_o(image, settings)
    if settings.get("route") == "P":
        return process_route_p(image, settings)
    if settings.get("route") == "Q":
        return process_route_q(image, settings)

    width, height = image.size
    calibrated = bool(settings.get("calibrated", True))
    chroma_blur = int(settings.get("chromaBlur", 1))
    grain = float(settings.get("grain", 0))
    edge_noise = float(settings.get("edgeNoise", 0))
    luma_noise = float(settings.get("lumaNoise", 18))
    resample = float(settings.get("resample", 0))
    residual_strength = float(settings.get("learnedResidual", 0))
    phlegethon_light = bool(settings.get("phlegethonLight", False))
    brightness = float(settings.get("brightness", -5))
    contrast = float(settings.get("contrast", 0.97))
    blue_shift = float(settings.get("blueShift", -1))

    image = apply_chroma_blur(image, chroma_blur)
    arr = np.asarray(image).astype(np.float32)
    old = np.asarray(image).astype(np.float32)

    if calibrated:
        arr[..., 0] = arr[..., 0] * AFFINE[0, 0] + AFFINE[0, 1]
        arr[..., 1] = arr[..., 1] * AFFINE[1, 0] + AFFINE[1, 1]
        arr[..., 2] = arr[..., 2] * AFFINE[2, 0] + AFFINE[2, 1]
    else:
        arr[..., 0] = (arr[..., 0] - 128) * contrast + 128 + brightness
        arr[..., 1] = (arr[..., 1] - 128) * contrast + 128 + brightness
        arr[..., 2] = (arr[..., 2] - 128) * contrast + 128 + brightness + blue_shift

    shared = (noise(width, height, 1) - 0.5) * grain
    luma = (noise(max(1, width // 2), max(1, height // 2), 5) - 0.5) * luma_noise
    luma_img = Image.fromarray(np.clip((luma + 32) * 4, 0, 255).astype(np.uint8), "L")
    luma_img = luma_img.resize((width, height), Image.Resampling.BICUBIC)
    luma = np.asarray(luma_img).astype(np.float32) / 4 - 32
    edge = edge_strength(old)
    arr[..., 0] += shared + luma + (noise(width, height, 2) - 0.5) * edge_noise * edge
    arr[..., 1] += shared + luma + (noise(width, height, 3) - 0.5) * edge_noise * edge
    arr[..., 2] += shared + luma + (noise(width, height, 4) - 0.5) * edge_noise * edge

    if residual_strength > 0:
        residual = calibration_residual()
        residual_img = Image.fromarray(np.clip(residual + 128, 0, 255).astype(np.uint8), "RGB")
        if residual_img.size != (width, height):
            residual_img = residual_img.resize((width, height), Image.Resampling.BICUBIC)
        residual_arr = np.asarray(residual_img).astype(np.float32) - 128
        arr += residual_arr * residual_strength

    if phlegethon_light:
        arr = adaptive_truthscan_layer(arr, old, settings)

    output = Image.fromarray(np.clip(arr, 0, 255).astype(np.uint8), "RGB")
    if resample > 0:
        scale = 1 - resample / 220
        small_size = (max(1, round(width * scale)), max(1, round(height * scale)))
        output = output.resize(small_size, Image.Resampling.LANCZOS)
        output = output.resize((width, height), Image.Resampling.BICUBIC)
        output = ImageOps.autocontrast(output, cutoff=0)
    return output


def samsung_exif():
    exif = Image.Exif()
    exif[271] = "SAMSUNG"
    exif[272] = "SM-F731U"
    exif[305] = "F731U1UEU1AWF1"
    exif[306] = "2026:02:28 14:22:00"
    exif[282] = TiffImagePlugin.IFDRational(72, 1)
    exif[283] = TiffImagePlugin.IFDRational(72, 1)
    return exif


def save_jpeg_bytes(output, settings):
    double_jpeg = bool(settings.get("doubleJpeg", False))
    if double_jpeg:
        first = io.BytesIO()
        output.save(
            first,
            format="JPEG",
            subsampling=2,
            qtables=PHLEGETHON_QTABLES,
            optimize=False,
            dpi=(72, 72),
        )
        first.seek(0)
        output = Image.open(first).convert("RGB")

    buf = io.BytesIO()
    save_kwargs = {
        "format": "JPEG",
        "subsampling": 2,
        "qtables": PHLEGETHON_QTABLES,
        "optimize": False,
        "dpi": (72, 72),
    }
    if bool(settings.get("writeExif", False)):
        save_kwargs["exif"] = samsung_exif()
    output.save(buf, **save_kwargs)
    return buf.getvalue()


def generic_candidate_settings(base):
    base = dict(base)
    auto = dict(base)
    auto.update({"route": "auto", "autoRoute": True, "writeExif": False})
    route_a = dict(base)
    route_a.update({"route": "A", "calibrated": True, "phlegethonLight": True, "writeExif": False, "lumaNoise": 18})
    route_b = dict(base)
    route_b.update(
        {
            "route": "B",
            "writeExif": False,
            "doubleJpeg": False,
            "routeBGain": 0.985,
            "routeBOffset": -2.0,
            "routeBBlueShift": -1.0,
            "routeBChromaBlur": 1,
        }
    )
    route_c = dict(base)
    route_c.update(
        {
            "route": "C",
            "writeExif": False,
            "doubleJpeg": False,
            "routeCChromaBlur": 1,
        }
    )
    variants = [
        ("auto_selected", "AUTO", {}),
        ("routeA_camera_luma18", "A", {}),
        ("routeA_camera_luma12", "A", {"lumaNoise": 12}),
        ("routeA_camera_luma22", "A", {"lumaNoise": 22, "chromaScale": 1.35}),
        ("routeD_snow_default", "D", {"routeDBackgroundDark": 4.8, "routeDLumaNoise": 13.5, "routeDHalfNoise": 8.0, "routeDCoarseNoise": 4.0, "routeDChroma": 1.15, "routeDSeed": 401}),
        ("routeD_snow_strong", "D", {"routeDBackgroundDark": 5.8, "routeDLumaNoise": 16.0, "routeDHalfNoise": 9.5, "routeDCoarseNoise": 5.0, "routeDChroma": 1.35, "routeDSeed": 409}),
        ("routeD_snow_soft", "D", {"routeDBackgroundDark": 3.6, "routeDLumaNoise": 10.5, "routeDHalfNoise": 6.0, "routeDCoarseNoise": 3.0, "routeDChroma": 0.95, "routeDSeed": 419}),
        ("routeD_snow_resample", "D", {"routeDBackgroundDark": 5.0, "routeDLumaNoise": 14.0, "routeDHalfNoise": 8.0, "routeDCoarseNoise": 4.0, "routeDChroma": 1.15, "routeDResample": 3, "routeDSeed": 421}),
        ("routeB_lowlight_texture", "B", {"routeBDenoise": 0.95, "routeBHfScale": 0.70, "routeBMidScale": 0.60, "routeBBlock": 4.0, "routeBGrain": 5.0, "routeBChroma": 1.6, "routeBOffset": -4.5, "routeBSeed": 127}),
        ("routeB_lowlight_preserve", "B", {"routeBDenoise": 0.55, "routeBHfScale": 0.92, "routeBMidScale": 0.30, "routeBBlock": 2.5, "routeBGrain": 2.5, "routeBChroma": 1.4, "routeBSeed": 103}),
        ("routeB_lowlight_double", "B", {"routeBDenoise": 0.95, "routeBHfScale": 0.70, "routeBMidScale": 0.60, "routeBBlock": 4.0, "routeBGrain": 5.0, "routeBChroma": 1.6, "doubleJpeg": True, "routeBSeed": 131}),
        ("routeC_phlegethon89_fit", "C", {"routeCDenoise": 0.75, "routeCHighKeep": 0.55, "routeCMidKeep": 0.72, "routeCBackgroundDark": 3.4, "routeCResidualFloor": 0.45, "routeCBlock": 1.2, "routeCChroma": 0.75, "routeCSeed": 211}),
        ("routeC_more_denoise", "C", {"routeCDenoise": 0.95, "routeCHighKeep": 0.42, "routeCMidKeep": 0.68, "routeCBackgroundDark": 3.4, "routeCResidualFloor": 0.35, "routeCBlock": 1.0, "routeCChroma": 0.65, "routeCSeed": 223}),
        ("routeC_less_denoise", "C", {"routeCDenoise": 0.55, "routeCHighKeep": 0.68, "routeCMidKeep": 0.78, "routeCBackgroundDark": 3.4, "routeCResidualFloor": 0.55, "routeCBlock": 1.2, "routeCChroma": 0.85, "routeCSeed": 227}),
        ("routeC_sky_dark", "C", {"routeCDenoise": 0.75, "routeCHighKeep": 0.55, "routeCMidKeep": 0.72, "routeCBackgroundDark": 5.2, "routeCResidualFloor": 0.45, "routeCBlock": 1.2, "routeCChroma": 0.75, "routeCSeed": 229}),
        ("routeC_sky_darker", "C", {"routeCDenoise": 0.85, "routeCHighKeep": 0.50, "routeCMidKeep": 0.70, "routeCBackgroundDark": 7.0, "routeCResidualFloor": 0.35, "routeCBlock": 1.0, "routeCChroma": 0.65, "routeCSeed": 233}),
        ("routeC_low_residual", "C", {"routeCDenoise": 1.10, "routeCHighKeep": 0.32, "routeCMidKeep": 0.58, "routeCBackgroundDark": 4.8, "routeCResidualFloor": 0.15, "routeCBlock": 0.4, "routeCChroma": 0.35, "routeCSeed": 263}),
        ("routeC_zeroish_residual", "C", {"routeCDenoise": 1.25, "routeCHighKeep": 0.25, "routeCMidKeep": 0.52, "routeCBackgroundDark": 5.2, "routeCResidualFloor": 0.05, "routeCBlock": 0.15, "routeCChroma": 0.25, "routeCSeed": 269}),
        ("routeC_resample2", "C", {"routeCDenoise": 0.85, "routeCHighKeep": 0.46, "routeCMidKeep": 0.66, "routeCBackgroundDark": 4.4, "routeCResidualFloor": 0.25, "routeCBlock": 1.0, "routeCChroma": 0.55, "routeCResample": 2, "routeCSeed": 283}),
        ("routeC_resample5", "C", {"routeCDenoise": 0.95, "routeCHighKeep": 0.38, "routeCMidKeep": 0.60, "routeCBackgroundDark": 4.8, "routeCResidualFloor": 0.18, "routeCBlock": 0.7, "routeCChroma": 0.45, "routeCResample": 5, "routeCSeed": 293}),
        ("routeC_double_fit", "C", {"routeCDenoise": 0.75, "routeCHighKeep": 0.55, "routeCMidKeep": 0.72, "routeCBackgroundDark": 3.4, "routeCResidualFloor": 0.45, "routeCBlock": 1.2, "routeCChroma": 0.75, "doubleJpeg": True, "routeCSeed": 307}),
        ("routeC_double_low_residual", "C", {"routeCDenoise": 1.10, "routeCHighKeep": 0.32, "routeCMidKeep": 0.58, "routeCBackgroundDark": 4.8, "routeCResidualFloor": 0.15, "routeCBlock": 0.4, "routeCChroma": 0.35, "doubleJpeg": True, "routeCSeed": 311}),
        ("routeC_strong_smooth", "C", {"routeCDenoise": 1.55, "routeCHighKeep": 0.18, "routeCMidKeep": 0.45, "routeCBackgroundDark": 5.8, "routeCResidualFloor": 0.05, "routeCBlock": 0.1, "routeCChroma": 0.2, "routeCSeed": 313}),
        ("routeC_strong_smooth_resample", "C", {"routeCDenoise": 1.55, "routeCHighKeep": 0.18, "routeCMidKeep": 0.45, "routeCBackgroundDark": 5.8, "routeCResidualFloor": 0.05, "routeCBlock": 0.1, "routeCChroma": 0.2, "routeCResample": 4, "routeCSeed": 317}),
        ("routeC_subject_preserve", "C", {"routeCDenoise": 0.90, "routeCEdgeProtect": 2.6, "routeCHighKeep": 0.60, "routeCMidKeep": 0.70, "routeCBackgroundDark": 5.6, "routeCResidualFloor": 0.25, "routeCBlock": 0.7, "routeCChroma": 0.45, "routeCSeed": 331}),
        ("routeC_subject_preserve_double", "C", {"routeCDenoise": 0.90, "routeCEdgeProtect": 2.6, "routeCHighKeep": 0.60, "routeCMidKeep": 0.70, "routeCBackgroundDark": 5.6, "routeCResidualFloor": 0.25, "routeCBlock": 0.7, "routeCChroma": 0.45, "doubleJpeg": True, "routeCSeed": 337}),
        ("routeC_extreme_phlegethon89", "C", {"routeCDenoise": 1.35, "routeCHighKeep": 0.22, "routeCMidKeep": 0.55, "routeCBackgroundDark": 7.5, "routeCResidualFloor": 0.10, "routeCBlock": 0.25, "routeCChroma": 0.25, "routeCResample": 3, "routeCSeed": 347}),
    ]
    results = []
    for name, route, patch in variants:
        settings = dict({"AUTO": auto, "A": route_a, "B": route_b, "C": route_c, "D": {"route": "D", "writeExif": False, "doubleJpeg": False, "routeDChromaBlur": 1}}[route])
        settings.update(patch)
        results.append((name, settings))
    return results


def adaptive_candidate_settings(image, base):
    base = dict(base)
    auto = auto_route_settings(image, {"route": "auto", "autoRoute": True, "writeExif": False})
    reason = auto.get("autoReason", "")
    if reason == "close_smooth_dark_face_portrait":
        center = dict(auto)
        center.pop("autoProfile", None)
        variants = [
            ("portraitO_soft", {"routeOSkinIrregular": 0.85, "routeORelight": 0.45, "routeOHair": 0.8, "routeOBg": 0.8, "routeOCfa": 0.25, "routeOClarity": 0.55, "routeOUnsharp": 45, "routeOSeed": 4101}),
            ("portraitO_balanced", {"routeOSkinIrregular": 1.25, "routeORelight": 0.75, "routeOHair": 1.2, "routeOBg": 1.1, "routeOCfa": 0.45, "routeOClarity": 0.75, "routeOUnsharp": 65, "routeOSeed": 4107}),
            ("portraitO_strong", {"routeOSkinIrregular": 1.65, "routeORelight": 1.00, "routeOHair": 1.6, "routeOBg": 1.4, "routeOCfa": 0.60, "routeOClarity": 0.95, "routeOUnsharp": 80, "routeOSeed": 4111}),
            ("portraitO_skin_heavy", {"routeOSkinIrregular": 2.20, "routeORelight": 0.80, "routeOHair": 1.1, "routeOBg": 1.0, "routeOCfa": 0.45, "routeOClarity": 1.10, "routeOUnsharp": 85, "routeOSeed": 4117}),
            ("portraitO_hair_heavy", {"routeOSkinIrregular": 1.35, "routeORelight": 0.70, "routeOHair": 2.4, "routeOBg": 1.2, "routeOCfa": 0.50, "routeOClarity": 0.95, "routeOUnsharp": 80, "routeOSeed": 4121}),
            ("portraitO_bg_heavy", {"routeOSkinIrregular": 1.20, "routeORelight": 0.65, "routeOHair": 1.2, "routeOBg": 2.2, "routeOCfa": 0.65, "routeOClarity": 0.80, "routeOUnsharp": 70, "routeOSeed": 4127}),
            ("portraitO_relight_heavy", {"routeOSkinIrregular": 1.40, "routeORelight": 1.60, "routeOHair": 1.2, "routeOBg": 1.2, "routeOCfa": 0.50, "routeOClarity": 0.90, "routeOUnsharp": 80, "routeOSeed": 4133}),
            ("portraitO_wide_face", {"routeOFaceRx": 0.28, "routeOFaceRy": 0.34, "routeOFaceOval": 1.05, "routeOSkinIrregular": 1.65, "routeORelight": 1.00, "routeOHair": 1.6, "routeOBg": 1.4, "routeOCfa": 0.60, "routeOClarity": 0.95, "routeOUnsharp": 80, "routeOSeed": 4137}),
            ("portraitO_tight_face", {"routeOFaceRx": 0.20, "routeOFaceRy": 0.26, "routeOFaceOval": 1.05, "routeOSkinIrregular": 2.00, "routeORelight": 0.90, "routeOHair": 1.4, "routeOBg": 1.3, "routeOCfa": 0.55, "routeOClarity": 1.05, "routeOUnsharp": 85, "routeOSeed": 4141}),
            ("portraitO_low_cfa", {"routeOSkinIrregular": 1.80, "routeORelight": 1.05, "routeOHair": 1.6, "routeOBg": 1.6, "routeOCfa": 0.15, "routeOClarity": 1.00, "routeOUnsharp": 85, "routeOSeed": 4147}),
            ("portraitO_high_cfa", {"routeOSkinIrregular": 1.50, "routeORelight": 0.90, "routeOHair": 1.5, "routeOBg": 1.5, "routeOCfa": 0.95, "routeOClarity": 0.95, "routeOUnsharp": 80, "routeOSeed": 4153}),
            ("portraitO_blemish_fine", {"routeOBlemishRadius": 1.4, "routeOSkinIrregular": 2.10, "routeORelight": 0.80, "routeOHair": 1.2, "routeOBg": 1.1, "routeOCfa": 0.45, "routeOClarity": 1.10, "routeOUnsharp": 90, "routeOSeed": 4159}),
            ("portraitO_blemish_coarse", {"routeOBlemishRadius": 5.0, "routeOSkinIrregular": 1.85, "routeORelight": 1.20, "routeOHair": 1.2, "routeOBg": 1.3, "routeOCfa": 0.45, "routeOClarity": 1.00, "routeOUnsharp": 85, "routeOSeed": 4163}),
            ("portraitO_extreme_clear", {"routeOSkinIrregular": 2.80, "routeORelight": 1.80, "routeOHair": 2.6, "routeOBg": 2.4, "routeOCfa": 1.00, "routeOClarity": 1.30, "routeOUnsharp": 100, "routeOSeed": 4169}),
            ("portraitO_double", {"routeOSkinIrregular": 1.65, "routeORelight": 1.00, "routeOHair": 1.6, "routeOBg": 1.4, "routeOCfa": 0.60, "routeOClarity": 0.95, "routeOUnsharp": 80, "routeOSeed": 4111, "doubleJpeg": True}),
            ("portraitO_donor_mix", {"route": "N", "routeNFaceCx": 0.50, "routeNFaceCy": 0.42, "routeNFaceRx": 0.24, "routeNFaceRy": 0.30, "routeNFaceResidual": 2.0, "routeNBgResidual": 2.2, "routeNDarkResidual": 2.4, "routeNLowResidual": 0.80, "routeNColorIrregular": 1.00, "routeNSkinTone": 1.35, "routeNCfa": 0.65, "routeNFaceClarity": 1.10, "routeNUnsharp": 90, "routeNSeed": 4171}),
        ]
        results = []
        for name, patch in variants:
            settings = dict(center)
            settings.update(patch)
            settings["writeExif"] = False
            results.append((name, settings))
        return results
    if reason == "cold_dark_snow_portrait":
        center = dict(auto)
        center.pop("autoProfile", None)
        variants = [
            ("coldSnowB_texture_double", {"route": "B", "doubleJpeg": True, "routeBDenoise": 0.55, "routeBHfScale": 0.92, "routeBMidScale": 0.30, "routeBBlock": 3.2, "routeBGrain": 3.8, "routeBChroma": 1.5, "routeBOffset": -3.2, "routeBResample": 2, "routeBSeed": 131}),
            ("coldSnowB_texture_strong", {"route": "B", "doubleJpeg": False, "routeBDenoise": 0.70, "routeBHfScale": 0.82, "routeBMidScale": 0.45, "routeBBlock": 4.8, "routeBGrain": 6.2, "routeBChroma": 1.8, "routeBOffset": -4.8, "routeBResample": 3, "routeBSeed": 139}),
            ("coldSnowB_preserve_face", {"route": "B", "doubleJpeg": False, "routeBDenoise": 0.42, "routeBHfScale": 1.02, "routeBMidScale": 0.26, "routeBBlock": 2.2, "routeBGrain": 2.8, "routeBChroma": 1.3, "routeBOffset": -2.6, "routeBResample": 1, "routeBSeed": 103}),
            ("coldSnowD_strong", {"route": "D", "writeExif": False, "doubleJpeg": False, "routeDBackgroundDark": 5.8, "routeDLumaNoise": 16.0, "routeDHalfNoise": 9.5, "routeDCoarseNoise": 5.0, "routeDChroma": 1.35, "routeDResample": 2, "routeDSeed": 409}),
            ("coldSnowD_resample", {"route": "D", "writeExif": False, "doubleJpeg": False, "routeDBackgroundDark": 5.0, "routeDLumaNoise": 14.0, "routeDHalfNoise": 8.0, "routeDCoarseNoise": 4.0, "routeDChroma": 1.15, "routeDResample": 4, "routeDSeed": 421}),
            ("coldSnowE_snow28_quality", {"route": "E", "doubleJpeg": False, "routeEShotNoise": 0.020, "routeEReadNoise": 0.0060, "routeEFixedNoise": 0.0025, "routeEDenoise": 0.55, "routeESharpen": 0.10, "routeECcm": 0.055, "routeEResample": 4, "routeESeed": 509}),
            ("coldSnowE_snow31_double", {"route": "E", "doubleJpeg": True, "routeEShotNoise": 0.022, "routeEReadNoise": 0.0065, "routeEFixedNoise": 0.0026, "routeEDenoise": 0.55, "routeESharpen": 0.11, "routeECcm": 0.055, "routeEResample": 4, "routeESeed": 557}),
            ("coldSnowE_cool_bloom", {"route": "E", "doubleJpeg": False, "routeEShotNoise": 0.017, "routeEReadNoise": 0.0050, "routeEFixedNoise": 0.0012, "routeEDenoise": 0.76, "routeESharpen": 0.040, "routeECcm": 0.030, "routeEInvWbR": 1.16, "routeEInvWbB": 0.84, "routeEHighlightBloom": 0.045, "routeEResample": 4, "routeESeed": 521}),
            ("coldSnowH_row18", {"route": "H", "routeHBaseLuma": 36, "routeHBaseResample": 1.0, "routeHBlend": 0.45, "routeHPixelScale": 1.2, "routeHMicroShift": 0.12, "routeHPrnu": 0.18, "routeHRow": 0.18, "routeHSharpen": 0.18, "routeHSeed": 701}),
            ("coldSnowH_row24", {"route": "H", "routeHBaseLuma": 36, "routeHBaseResample": 1.0, "routeHBlend": 0.45, "routeHPixelScale": 1.2, "routeHMicroShift": 0.12, "routeHPrnu": 0.18, "routeHRow": 0.24, "routeHSharpen": 0.18, "routeHSeed": 701}),
            ("coldSnowI_subtle", {"route": "I", "routeIBaseLuma": 36, "routeIBaseResample": 1.0, "routeIBaseBlend": 0.45, "routeIBasePixelScale": 1.2, "routeIBaseMicroShift": 0.12, "routeIBasePrnu": 0.18, "routeIBaseRow": 0.18, "routeIBaseSharpen": 0.18, "routeIRotate": 0.04, "routeIOpticalScale": 1.2, "routeILensShade": 0.10, "routeIChromaticAberration": 0.04, "routeILocalContrast": 0.03, "routeISeed": 701}),
            ("coldSnowI_score", {"route": "I", "routeIBaseLuma": 36, "routeIBaseResample": 1.0, "routeIBaseBlend": 0.62, "routeIBasePixelScale": 1.6, "routeIBaseMicroShift": 0.16, "routeIBasePrnu": 0.22, "routeIBaseRow": 0.18, "routeIBaseSharpen": 0.14, "routeIRotate": 0.06, "routeIOpticalScale": 1.5, "routeILensShade": 0.12, "routeIChromaticAberration": 0.05, "routeILocalContrast": 0.02, "routeISeed": 701}),
        ]
        results = []
        for name, patch in variants:
            settings = dict(center)
            settings.update(patch)
            settings["writeExif"] = False
            results.append((name, settings))
        return results
    if reason == "dark_smooth_low_residual_surface":
        center = dict(auto)
        center.pop("autoProfile", None)
        variants = [
            ("darkQ_ref_exact_like_his", {"route": "Q", "routeQReferenceBlend": 1.00, "routeQResidualScale": 1.00, "routeQUnsharp": 0, "routeQFine": 0.0, "doubleJpeg": False}),
            ("darkQ_ref_85_sharp", {"route": "Q", "routeQReferenceBlend": 0.85, "routeQResidualScale": 1.00, "routeQUnsharp": 35, "routeQFine": 0.0, "doubleJpeg": False}),
            ("darkQ_ref_70_sharp", {"route": "Q", "routeQReferenceBlend": 0.70, "routeQResidualScale": 1.00, "routeQUnsharp": 45, "routeQFine": 0.0, "doubleJpeg": False}),
            ("darkQ_affine_only_sharp", {"route": "Q", "routeQReferenceBlend": 0.00, "routeQUnsharp": 45, "routeQFine": 0.0, "doubleJpeg": False}),
            ("darkQ_affine_fine_sharp", {"route": "Q", "routeQReferenceBlend": 0.00, "routeQUnsharp": 45, "routeQFine": 0.8, "routeQSeed": 7001, "doubleJpeg": False}),
            ("darkQ_ref_85_double", {"route": "Q", "routeQReferenceBlend": 0.85, "routeQResidualScale": 1.00, "routeQUnsharp": 35, "routeQFine": 0.0, "doubleJpeg": True}),
            ("darkE_35_wb_cooler_anchor", {"route": "E", "routeEShotNoise": 0.018, "routeEReadNoise": 0.0052, "routeEFixedNoise": 0.0014, "routeEDenoise": 0.70, "routeESharpen": 0.055, "routeECcm": 0.045, "routeEInvWbR": 1.12, "routeEInvWbB": 0.88, "routeEResample": 4, "routeESeed": 509}),
            ("darkE_35_cool_clean", {"route": "E", "routeEShotNoise": 0.015, "routeEReadNoise": 0.0046, "routeEFixedNoise": 0.0009, "routeEDenoise": 0.78, "routeESharpen": 0.035, "routeECcm": 0.030, "routeEInvWbR": 1.12, "routeEInvWbB": 0.88, "routeEResample": 4, "routeESeed": 509}),
            ("darkE_35_cool_low_ccm", {"route": "E", "routeEShotNoise": 0.018, "routeEReadNoise": 0.0050, "routeEFixedNoise": 0.0011, "routeEDenoise": 0.72, "routeESharpen": 0.045, "routeECcm": 0.020, "routeEInvWbR": 1.12, "routeEInvWbB": 0.88, "routeEResample": 4, "routeESeed": 509}),
            ("darkE_35_cool_more_denoise", {"route": "E", "routeEShotNoise": 0.016, "routeEReadNoise": 0.0048, "routeEFixedNoise": 0.0010, "routeEDenoise": 0.86, "routeESharpen": 0.025, "routeECcm": 0.025, "routeEInvWbR": 1.12, "routeEInvWbB": 0.88, "routeEResample": 4, "routeESeed": 509}),
            ("darkE_35_cool_less_denoise", {"route": "E", "routeEShotNoise": 0.020, "routeEReadNoise": 0.0054, "routeEFixedNoise": 0.0014, "routeEDenoise": 0.62, "routeESharpen": 0.070, "routeECcm": 0.045, "routeEInvWbR": 1.12, "routeEInvWbB": 0.88, "routeEResample": 4, "routeESeed": 509}),
            ("darkE_35_cool_resample3", {"route": "E", "routeEShotNoise": 0.018, "routeEReadNoise": 0.0052, "routeEFixedNoise": 0.0014, "routeEDenoise": 0.70, "routeESharpen": 0.055, "routeECcm": 0.045, "routeEInvWbR": 1.12, "routeEInvWbB": 0.88, "routeEResample": 3, "routeESeed": 509}),
            ("darkE_35_cool_resample5", {"route": "E", "routeEShotNoise": 0.018, "routeEReadNoise": 0.0052, "routeEFixedNoise": 0.0014, "routeEDenoise": 0.70, "routeESharpen": 0.050, "routeECcm": 0.040, "routeEInvWbR": 1.12, "routeEInvWbB": 0.88, "routeEResample": 5, "routeESeed": 521}),
            ("darkE_35_cooler_114_086", {"route": "E", "routeEShotNoise": 0.018, "routeEReadNoise": 0.0052, "routeEFixedNoise": 0.0014, "routeEDenoise": 0.70, "routeESharpen": 0.050, "routeECcm": 0.040, "routeEInvWbR": 1.14, "routeEInvWbB": 0.86, "routeEResample": 4, "routeESeed": 509}),
            ("darkE_35_cooler_116_084", {"route": "E", "routeEShotNoise": 0.017, "routeEReadNoise": 0.0050, "routeEFixedNoise": 0.0012, "routeEDenoise": 0.76, "routeESharpen": 0.040, "routeECcm": 0.030, "routeEInvWbR": 1.16, "routeEInvWbB": 0.84, "routeEResample": 4, "routeESeed": 509}),
            ("darkE_35_less_cool_110_090", {"route": "E", "routeEShotNoise": 0.018, "routeEReadNoise": 0.0052, "routeEFixedNoise": 0.0012, "routeEDenoise": 0.72, "routeESharpen": 0.050, "routeECcm": 0.035, "routeEInvWbR": 1.10, "routeEInvWbB": 0.90, "routeEResample": 4, "routeESeed": 509}),
            ("darkE_35_cool_bloom_soft", {"route": "E", "routeEShotNoise": 0.015, "routeEReadNoise": 0.0046, "routeEFixedNoise": 0.0009, "routeEDenoise": 0.82, "routeESharpen": 0.025, "routeECcm": 0.025, "routeEInvWbR": 1.12, "routeEInvWbB": 0.88, "routeEHighlightBloom": 0.045, "routeEHighlightBlur": 5.0, "routeEResample": 4, "routeESeed": 521}),
            ("darkE_35_seed503", {"route": "E", "routeEShotNoise": 0.018, "routeEReadNoise": 0.0052, "routeEFixedNoise": 0.0014, "routeEDenoise": 0.70, "routeESharpen": 0.055, "routeECcm": 0.045, "routeEInvWbR": 1.12, "routeEInvWbB": 0.88, "routeEResample": 4, "routeESeed": 503}),
            ("darkA_phlegethon26_luma6_r1", {"route": "A", "calibrated": True, "phlegethonLight": False, "lumaNoise": 6, "chromaScale": 0.0, "residualScale": 0.0, "resample": 1, "doubleJpeg": False}),
            ("darkA_phlegethon26_luma6_r4", {"route": "A", "calibrated": True, "phlegethonLight": False, "lumaNoise": 6, "chromaScale": 0.0, "residualScale": 0.0, "resample": 4, "doubleJpeg": False}),
            ("darkA_phlegethon26_luma4_r1", {"route": "A", "calibrated": True, "phlegethonLight": False, "lumaNoise": 4, "chromaScale": 0.0, "residualScale": 0.0, "resample": 1, "doubleJpeg": False}),
            ("darkA_phlegethon26_luma8_r1", {"route": "A", "calibrated": True, "phlegethonLight": False, "lumaNoise": 8, "chromaScale": 0.0, "residualScale": 0.0, "resample": 1, "doubleJpeg": False}),
            ("darkA_phlegethon26_clean_r1", {"route": "A", "calibrated": True, "phlegethonLight": False, "lumaNoise": 0, "chromaScale": 0.0, "residualScale": 0.0, "resample": 1, "doubleJpeg": False}),
            ("darkA_phlegethon26_double", {"route": "A", "calibrated": True, "phlegethonLight": False, "lumaNoise": 6, "chromaScale": 0.0, "residualScale": 0.0, "resample": 1, "doubleJpeg": True}),
            ("darkE_auto_center", {}),
            ("darkE_balanced_anchor", {"route": "E", "routeEShotNoise": 0.020, "routeEReadNoise": 0.0060, "routeEFixedNoise": 0.0025, "routeEDenoise": 0.55, "routeESharpen": 0.10, "routeECcm": 0.055, "routeEResample": 4, "routeESeed": 509}),
            ("darkE_low_fixed", {"route": "E", "routeEShotNoise": 0.020, "routeEReadNoise": 0.0055, "routeEFixedNoise": 0.0012, "routeEDenoise": 0.62, "routeESharpen": 0.065, "routeECcm": 0.050, "routeEResample": 4, "routeESeed": 509}),
            ("darkE_clean_denoise", {"route": "E", "routeEShotNoise": 0.017, "routeEReadNoise": 0.0048, "routeEFixedNoise": 0.0012, "routeEDenoise": 0.78, "routeESharpen": 0.045, "routeECcm": 0.045, "routeEResample": 4, "routeESeed": 509}),
            ("darkE_soft_resample3", {"route": "E", "routeEShotNoise": 0.018, "routeEReadNoise": 0.0050, "routeEFixedNoise": 0.0014, "routeEDenoise": 0.70, "routeESharpen": 0.050, "routeECcm": 0.045, "routeEResample": 3, "routeESeed": 503}),
            ("darkE_soft_resample5", {"route": "E", "routeEShotNoise": 0.018, "routeEReadNoise": 0.0050, "routeEFixedNoise": 0.0014, "routeEDenoise": 0.70, "routeESharpen": 0.050, "routeECcm": 0.045, "routeEResample": 5, "routeESeed": 521}),
            ("darkE_less_shot", {"route": "E", "routeEShotNoise": 0.014, "routeEReadNoise": 0.0048, "routeEFixedNoise": 0.0012, "routeEDenoise": 0.66, "routeESharpen": 0.055, "routeECcm": 0.045, "routeEResample": 4, "routeESeed": 503}),
            ("darkE_more_shot_clean", {"route": "E", "routeEShotNoise": 0.024, "routeEReadNoise": 0.0052, "routeEFixedNoise": 0.0010, "routeEDenoise": 0.82, "routeESharpen": 0.040, "routeECcm": 0.040, "routeEResample": 4, "routeESeed": 541}),
            ("darkE_low_ccm", {"route": "E", "routeEShotNoise": 0.018, "routeEReadNoise": 0.0052, "routeEFixedNoise": 0.0014, "routeEDenoise": 0.70, "routeESharpen": 0.055, "routeECcm": 0.025, "routeEResample": 4, "routeESeed": 509}),
            ("darkE_mid_ccm", {"route": "E", "routeEShotNoise": 0.018, "routeEReadNoise": 0.0052, "routeEFixedNoise": 0.0014, "routeEDenoise": 0.70, "routeESharpen": 0.055, "routeECcm": 0.065, "routeEResample": 4, "routeESeed": 509}),
            ("darkE_toe_low", {"route": "E", "routeEShotNoise": 0.018, "routeEReadNoise": 0.0052, "routeEFixedNoise": 0.0014, "routeEDenoise": 0.70, "routeESharpen": 0.055, "routeECcm": 0.045, "routeEToe": 0.010, "routeEShoulder": 0.025, "routeEResample": 4, "routeESeed": 509}),
            ("darkE_toe_high", {"route": "E", "routeEShotNoise": 0.018, "routeEReadNoise": 0.0052, "routeEFixedNoise": 0.0014, "routeEDenoise": 0.70, "routeESharpen": 0.055, "routeECcm": 0.045, "routeEToe": 0.030, "routeEShoulder": 0.032, "routeEResample": 4, "routeESeed": 509}),
            ("darkE_highlight_bloom", {"route": "E", "routeEShotNoise": 0.018, "routeEReadNoise": 0.0052, "routeEFixedNoise": 0.0014, "routeEDenoise": 0.70, "routeESharpen": 0.050, "routeECcm": 0.045, "routeEHighlightBloom": 0.045, "routeEHighlightBlur": 4.5, "routeEResample": 4, "routeESeed": 509}),
            ("darkE_bloom_soft", {"route": "E", "routeEShotNoise": 0.016, "routeEReadNoise": 0.0048, "routeEFixedNoise": 0.0011, "routeEDenoise": 0.80, "routeESharpen": 0.035, "routeECcm": 0.035, "routeEHighlightBloom": 0.060, "routeEHighlightBlur": 5.5, "routeEResample": 4, "routeESeed": 521}),
            ("darkE_wb_warmer", {"route": "E", "routeEShotNoise": 0.018, "routeEReadNoise": 0.0052, "routeEFixedNoise": 0.0014, "routeEDenoise": 0.70, "routeESharpen": 0.055, "routeECcm": 0.045, "routeEInvWbR": 1.04, "routeEInvWbB": 0.96, "routeEResample": 4, "routeESeed": 509}),
            ("darkE_wb_cooler", {"route": "E", "routeEShotNoise": 0.018, "routeEReadNoise": 0.0052, "routeEFixedNoise": 0.0014, "routeEDenoise": 0.70, "routeESharpen": 0.055, "routeECcm": 0.045, "routeEInvWbR": 1.12, "routeEInvWbB": 0.88, "routeEResample": 4, "routeESeed": 509}),
            ("darkE_seed503", {"route": "E", "routeEShotNoise": 0.018, "routeEReadNoise": 0.0052, "routeEFixedNoise": 0.0014, "routeEDenoise": 0.70, "routeESharpen": 0.055, "routeECcm": 0.045, "routeEResample": 4, "routeESeed": 503}),
            ("darkE_seed521", {"route": "E", "routeEShotNoise": 0.018, "routeEReadNoise": 0.0052, "routeEFixedNoise": 0.0014, "routeEDenoise": 0.70, "routeESharpen": 0.055, "routeECcm": 0.045, "routeEResample": 4, "routeESeed": 521}),
            ("darkE_seed557", {"route": "E", "routeEShotNoise": 0.018, "routeEReadNoise": 0.0052, "routeEFixedNoise": 0.0014, "routeEDenoise": 0.70, "routeESharpen": 0.055, "routeECcm": 0.045, "routeEResample": 4, "routeESeed": 557}),
            ("darkE_channel_low_noise_bloom", {"route": "E", "routeEShotNoise": 0.015, "routeEReadNoise": 0.0045, "routeEFixedNoise": 0.0008, "routeEDenoise": 0.85, "routeESharpen": 0.030, "routeECcm": 0.030, "routeEToe": 0.024, "routeEHighlightBloom": 0.055, "routeEResample": 4, "routeESeed": 541}),
            ("darkE_channel_texture_only", {"route": "E", "routeEShotNoise": 0.026, "routeEReadNoise": 0.0038, "routeEFixedNoise": 0.0007, "routeEDenoise": 0.90, "routeESharpen": 0.020, "routeECcm": 0.020, "routeEHighlightBloom": 0.020, "routeEResample": 4, "routeESeed": 503}),
            ("darkE_double_sanity", {"route": "E", "routeEShotNoise": 0.018, "routeEReadNoise": 0.0052, "routeEFixedNoise": 0.0014, "routeEDenoise": 0.70, "routeESharpen": 0.055, "routeECcm": 0.045, "routeEResample": 4, "doubleJpeg": True, "routeESeed": 509}),
        ]
        results = []
        for name, patch in variants:
            settings = dict(center)
            settings.update(patch)
            if "route" not in patch:
                settings["route"] = "E"
            settings["writeExif"] = False
            results.append((name, settings))
        return results
    if reason == "warm_indoor_flash_smooth_surface":
        center = dict(auto)
        center.pop("autoProfile", None)
        variants = [
            ("flashE_auto_center", {}),
            ("flashE_balanced", {"route": "E", "routeEShotNoise": 0.020, "routeEReadNoise": 0.0054, "routeEFixedNoise": 0.0012, "routeEDenoise": 0.76, "routeESharpen": 0.055, "routeECcm": 0.035, "routeEToe": 0.024, "routeEShoulder": 0.026, "routeEHighlightBloom": 0.025, "routeEResample": 4, "routeESeed": 541}),
            ("flashE_clean_low_fixed", {"route": "E", "routeEShotNoise": 0.018, "routeEReadNoise": 0.0048, "routeEFixedNoise": 0.0007, "routeEDenoise": 0.86, "routeESharpen": 0.030, "routeECcm": 0.025, "routeEToe": 0.028, "routeEShoulder": 0.024, "routeEHighlightBloom": 0.035, "routeEResample": 4, "routeESeed": 541}),
            ("flashE_preserve_edges", {"route": "E", "routeEShotNoise": 0.018, "routeEReadNoise": 0.0050, "routeEFixedNoise": 0.0010, "routeEDenoise": 0.58, "routeESharpen": 0.105, "routeECcm": 0.040, "routeEToe": 0.020, "routeEShoulder": 0.028, "routeEHighlightBloom": 0.020, "routeEResample": 3, "routeESeed": 509}),
            ("flashE_more_sensor", {"route": "E", "routeEShotNoise": 0.026, "routeEReadNoise": 0.0062, "routeEFixedNoise": 0.0011, "routeEDenoise": 0.82, "routeESharpen": 0.040, "routeECcm": 0.030, "routeEToe": 0.028, "routeEShoulder": 0.024, "routeEHighlightBloom": 0.030, "routeEResample": 4, "routeESeed": 503}),
            ("flashE_resample5", {"route": "E", "routeEShotNoise": 0.020, "routeEReadNoise": 0.0054, "routeEFixedNoise": 0.0010, "routeEDenoise": 0.78, "routeESharpen": 0.045, "routeECcm": 0.030, "routeEToe": 0.026, "routeEShoulder": 0.026, "routeEHighlightBloom": 0.030, "routeEResample": 5, "routeESeed": 521}),
            ("flashE_resample2", {"route": "E", "routeEShotNoise": 0.020, "routeEReadNoise": 0.0054, "routeEFixedNoise": 0.0012, "routeEDenoise": 0.68, "routeESharpen": 0.075, "routeECcm": 0.035, "routeEToe": 0.024, "routeEShoulder": 0.026, "routeEHighlightBloom": 0.020, "routeEResample": 2, "routeESeed": 509}),
            ("flashE_warm_wb", {"route": "E", "routeEShotNoise": 0.020, "routeEReadNoise": 0.0054, "routeEFixedNoise": 0.0010, "routeEDenoise": 0.78, "routeESharpen": 0.045, "routeECcm": 0.030, "routeEInvWbR": 1.02, "routeEInvWbB": 0.98, "routeEToe": 0.026, "routeEShoulder": 0.026, "routeEHighlightBloom": 0.030, "routeEResample": 4, "routeESeed": 541}),
            ("flashE_cool_wb", {"route": "E", "routeEShotNoise": 0.020, "routeEReadNoise": 0.0054, "routeEFixedNoise": 0.0010, "routeEDenoise": 0.78, "routeESharpen": 0.045, "routeECcm": 0.030, "routeEInvWbR": 1.12, "routeEInvWbB": 0.88, "routeEToe": 0.026, "routeEShoulder": 0.026, "routeEHighlightBloom": 0.030, "routeEResample": 4, "routeESeed": 541}),
            ("flashE_bloom_soft", {"route": "E", "routeEShotNoise": 0.017, "routeEReadNoise": 0.0046, "routeEFixedNoise": 0.0008, "routeEDenoise": 0.88, "routeESharpen": 0.025, "routeECcm": 0.020, "routeEToe": 0.030, "routeEShoulder": 0.022, "routeEHighlightBloom": 0.070, "routeEHighlightBlur": 5.5, "routeEResample": 4, "routeESeed": 521}),
            ("flashE_no_bloom", {"route": "E", "routeEShotNoise": 0.020, "routeEReadNoise": 0.0054, "routeEFixedNoise": 0.0012, "routeEDenoise": 0.76, "routeESharpen": 0.055, "routeECcm": 0.035, "routeEToe": 0.024, "routeEShoulder": 0.026, "routeEHighlightBloom": 0.0, "routeEResample": 4, "routeESeed": 541}),
            ("flashE_seed503", {"route": "E", "routeEShotNoise": 0.020, "routeEReadNoise": 0.0054, "routeEFixedNoise": 0.0012, "routeEDenoise": 0.76, "routeESharpen": 0.055, "routeECcm": 0.035, "routeEToe": 0.024, "routeEShoulder": 0.026, "routeEHighlightBloom": 0.025, "routeEResample": 4, "routeESeed": 503}),
            ("flashE_seed557", {"route": "E", "routeEShotNoise": 0.020, "routeEReadNoise": 0.0054, "routeEFixedNoise": 0.0012, "routeEDenoise": 0.76, "routeESharpen": 0.055, "routeECcm": 0.035, "routeEToe": 0.024, "routeEShoulder": 0.026, "routeEHighlightBloom": 0.025, "routeEResample": 4, "routeESeed": 557}),
            ("flashE_double_check", {"route": "E", "routeEShotNoise": 0.020, "routeEReadNoise": 0.0054, "routeEFixedNoise": 0.0010, "routeEDenoise": 0.78, "routeESharpen": 0.045, "routeECcm": 0.030, "routeEToe": 0.026, "routeEShoulder": 0.026, "routeEHighlightBloom": 0.030, "routeEResample": 4, "doubleJpeg": True, "routeESeed": 541}),
            ("flashA_luma18_check", {"route": "A", "phlegethonLight": False, "lumaNoise": 18, "chromaScale": 1.2, "residualScale": 1.0, "resample": 0, "doubleJpeg": False}),
            ("flashD_strong_check", {"route": "D", "routeDBackgroundDark": 5.8, "routeDLumaNoise": 16.0, "routeDHalfNoise": 9.5, "routeDCoarseNoise": 5.0, "routeDChroma": 1.35, "routeDSeed": 409}),
        ]
        results = []
        for name, patch in variants:
            settings = dict(center)
            settings.update(patch)
            settings["writeExif"] = False
            results.append((name, settings))
        return results
    if reason == "bright_cold_smooth_low_residual_surface":
        center = dict(auto)
        center.pop("autoProfile", None)
        route_c_quality = {
            "route": "C",
            "writeExif": False,
            "routeCDenoise": 1.55,
            "routeCEdgeProtect": 2.07,
            "routeCHighKeep": 0.150,
            "routeCMidKeep": 0.44,
            "routeCChroma": 0.24,
            "routeCResidualFloor": 0.05,
            "routeCBlock": 0.10,
            "routeCResample": 4,
        }
        variants = [
            ("brightE_auto_quality", {}),
            ("brightE_balanced_anchor", {"route": "E", "routeEShotNoise": 0.020, "routeEReadNoise": 0.0060, "routeEFixedNoise": 0.0025, "routeEDenoise": 0.55, "routeESharpen": 0.10, "routeECcm": 0.055, "routeEResample": 4, "routeESeed": 509}),
            ("brightE_soft_low_noise", {"route": "E", "routeEShotNoise": 0.014, "routeEReadNoise": 0.0045, "routeEFixedNoise": 0.0018, "routeEDenoise": 0.50, "routeESharpen": 0.08, "routeECcm": 0.040, "routeEResample": 3, "routeESeed": 503}),
            ("brightE_preserve_sharp", {"route": "E", "routeEShotNoise": 0.018, "routeEReadNoise": 0.0056, "routeEFixedNoise": 0.0021, "routeEDenoise": 0.42, "routeESharpen": 0.14, "routeECcm": 0.050, "routeEResample": 3, "routeESeed": 509}),
            ("brightE_low_resample", {"route": "E", "routeEShotNoise": 0.020, "routeEReadNoise": 0.0060, "routeEFixedNoise": 0.0025, "routeEDenoise": 0.52, "routeESharpen": 0.11, "routeECcm": 0.055, "routeEResample": 2, "routeESeed": 509}),
            ("brightE_resample5_sanity", {"route": "E", "routeEShotNoise": 0.020, "routeEReadNoise": 0.0060, "routeEFixedNoise": 0.0025, "routeEDenoise": 0.55, "routeESharpen": 0.09, "routeECcm": 0.055, "routeEResample": 5, "routeESeed": 521}),
            ("brightE_less_ccm", {"route": "E", "routeEShotNoise": 0.020, "routeEReadNoise": 0.0060, "routeEFixedNoise": 0.0025, "routeEDenoise": 0.55, "routeESharpen": 0.10, "routeECcm": 0.035, "routeEResample": 4, "routeESeed": 509}),
            ("brightE_more_ccm", {"route": "E", "routeEShotNoise": 0.020, "routeEReadNoise": 0.0060, "routeEFixedNoise": 0.0025, "routeEDenoise": 0.55, "routeESharpen": 0.10, "routeECcm": 0.075, "routeEResample": 4, "routeESeed": 509}),
            ("brightE_warmer", {"route": "E", "routeEShotNoise": 0.020, "routeEReadNoise": 0.0060, "routeEFixedNoise": 0.0025, "routeEDenoise": 0.55, "routeESharpen": 0.10, "routeECcm": 0.055, "routeEInvWbR": 1.04, "routeEInvWbB": 0.96, "routeEResample": 4, "routeESeed": 509}),
            ("brightE_cooler", {"route": "E", "routeEShotNoise": 0.020, "routeEReadNoise": 0.0060, "routeEFixedNoise": 0.0025, "routeEDenoise": 0.55, "routeESharpen": 0.10, "routeECcm": 0.055, "routeEInvWbR": 1.12, "routeEInvWbB": 0.88, "routeEResample": 4, "routeESeed": 509}),
            ("brightE_seed503", {"route": "E", "routeEShotNoise": 0.020, "routeEReadNoise": 0.0060, "routeEFixedNoise": 0.0025, "routeEDenoise": 0.55, "routeESharpen": 0.10, "routeECcm": 0.055, "routeEResample": 4, "routeESeed": 503}),
            ("brightE_seed557", {"route": "E", "routeEShotNoise": 0.020, "routeEReadNoise": 0.0060, "routeEFixedNoise": 0.0025, "routeEDenoise": 0.55, "routeESharpen": 0.10, "routeECcm": 0.055, "routeEResample": 4, "routeESeed": 557}),
            ("brightE_double_score_first", {"route": "E", "routeEShotNoise": 0.022, "routeEReadNoise": 0.0065, "routeEFixedNoise": 0.0026, "routeEDenoise": 0.55, "routeESharpen": 0.11, "routeECcm": 0.055, "routeEResample": 4, "doubleJpeg": True, "routeESeed": 557}),
            ("brightC_quality_fallback", route_c_quality),
        ]
        results = []
        for name, patch in variants:
            settings = dict(center)
            settings.update(patch)
            settings["writeExif"] = False
            results.append((name, settings))
        return results
    if reason == "sharp_snow_camera_residual":
        center = dict(auto)
        center.pop("autoProfile", None)
        variants = [
            ("sharpSnowH_row18_anchor", {"route": "H", "routeHBaseLuma": 36, "routeHBaseResample": 1.0, "routeHBlend": 0.45, "routeHPixelScale": 1.2, "routeHMicroShift": 0.12, "routeHPrnu": 0.18, "routeHRow": 0.18, "routeHSharpen": 0.18, "routeHSeed": 701}),
            ("sharpSnowH_row16", {"route": "H", "routeHBaseLuma": 36, "routeHBaseResample": 1.0, "routeHBlend": 0.45, "routeHPixelScale": 1.2, "routeHMicroShift": 0.12, "routeHPrnu": 0.18, "routeHRow": 0.16, "routeHSharpen": 0.18, "routeHSeed": 701}),
            ("sharpSnowH_row24", {"route": "H", "routeHBaseLuma": 36, "routeHBaseResample": 1.0, "routeHBlend": 0.45, "routeHPixelScale": 1.2, "routeHMicroShift": 0.12, "routeHPrnu": 0.18, "routeHRow": 0.24, "routeHSharpen": 0.18, "routeHSeed": 701}),
            ("sharpSnowI_rotate004", {"route": "I", "routeIRotate": 0.04, "routeIOpticalScale": 1.2, "routeILensShade": 0.10, "routeIChromaticAberration": 0.04, "routeILocalContrast": 0.03, "routeISeed": 701}),
            ("sharpSnowI_rotate008", {"route": "I", "routeIRotate": 0.08, "routeIOpticalScale": 1.5, "routeILensShade": 0.12, "routeIChromaticAberration": 0.05, "routeILocalContrast": 0.03, "routeISeed": 701}),
            ("sharpSnowI_rotate012", {"route": "I", "routeIRotate": 0.12, "routeIOpticalScale": 1.8, "routeILensShade": 0.15, "routeIChromaticAberration": 0.05, "routeILocalContrast": 0.03, "routeISeed": 701}),
            ("sharpSnowI_scale20", {"route": "I", "routeIRotate": 0.04, "routeIOpticalScale": 2.0, "routeILensShade": 0.12, "routeIChromaticAberration": 0.05, "routeILocalContrast": 0.03, "routeISeed": 701}),
            ("sharpSnowI_scale30", {"route": "I", "routeIRotate": 0.04, "routeIOpticalScale": 3.0, "routeILensShade": 0.12, "routeIChromaticAberration": 0.05, "routeILocalContrast": 0.03, "routeISeed": 701}),
            ("sharpSnowI_lens25", {"route": "I", "routeIRotate": 0.04, "routeIOpticalScale": 1.5, "routeILensShade": 0.25, "routeIChromaticAberration": 0.05, "routeILocalContrast": 0.03, "routeISeed": 701}),
            ("sharpSnowI_ca08", {"route": "I", "routeIRotate": 0.04, "routeIOpticalScale": 1.5, "routeILensShade": 0.12, "routeIChromaticAberration": 0.08, "routeILocalContrast": 0.03, "routeISeed": 701}),
            ("sharpSnowI_ca12", {"route": "I", "routeIRotate": 0.04, "routeIOpticalScale": 1.5, "routeILensShade": 0.12, "routeIChromaticAberration": 0.12, "routeILocalContrast": 0.03, "routeISeed": 701}),
            ("sharpSnowI_contrast06", {"route": "I", "routeIRotate": 0.04, "routeIOpticalScale": 1.5, "routeILensShade": 0.12, "routeIChromaticAberration": 0.05, "routeILocalContrast": 0.06, "routeISeed": 701}),
            ("sharpSnowI_row16_rotate", {"route": "I", "routeIBaseRow": 0.16, "routeIRotate": 0.06, "routeIOpticalScale": 1.5, "routeILensShade": 0.12, "routeIChromaticAberration": 0.05, "routeILocalContrast": 0.03, "routeISeed": 701}),
            ("sharpSnowI_row24_rotate", {"route": "I", "routeIBaseRow": 0.24, "routeIRotate": 0.06, "routeIOpticalScale": 1.5, "routeILensShade": 0.12, "routeIChromaticAberration": 0.05, "routeILocalContrast": 0.03, "routeISeed": 701}),
            ("sharpSnowI_pixel16_rotate", {"route": "I", "routeIBasePixelScale": 1.6, "routeIBaseBlend": 0.50, "routeIBaseMicroShift": 0.14, "routeIRotate": 0.06, "routeIOpticalScale": 1.5, "routeILensShade": 0.12, "routeIChromaticAberration": 0.05, "routeILocalContrast": 0.03, "routeISeed": 701}),
            ("sharpSnowI_blend62_rotate", {"route": "I", "routeIBasePixelScale": 1.6, "routeIBaseBlend": 0.62, "routeIBaseMicroShift": 0.16, "routeIBasePrnu": 0.22, "routeIBaseSharpen": 0.14, "routeIRotate": 0.06, "routeIOpticalScale": 1.5, "routeILensShade": 0.12, "routeIChromaticAberration": 0.05, "routeILocalContrast": 0.02, "routeISeed": 701}),
            ("sharpSnowI_seed709", {"route": "I", "routeIRotate": 0.04, "routeIOpticalScale": 1.5, "routeILensShade": 0.12, "routeIChromaticAberration": 0.05, "routeILocalContrast": 0.03, "routeISeed": 709}),
            ("sharpSnowI_no_rotate_lens", {"route": "I", "routeIRotate": 0.0, "routeIOpticalScale": 0.0, "routeILensShade": 0.18, "routeIChromaticAberration": 0.08, "routeILocalContrast": 0.04, "routeISeed": 701}),
        ]
        results = []
        for name, patch in variants:
            settings = dict(center)
            settings.update(patch)
            settings["writeExif"] = False
            results.append((name, settings))
        return results
    if reason == "high_detail_alley_portrait":
        center = dict(auto)
        center.pop("autoProfile", None)
        variants_p = [
            ("alleyP_snow_only", {"route": "P", "routePSnow": 1.4, "routePWall": 0.0, "routePLight": 0.0, "routePAsym": 0.0, "routePSkin": 0.0, "routePHair": 0.0, "routePClarity": 0.55, "routePUnsharp": 55, "routePSeed": 5101}),
            ("alleyP_wall_only", {"route": "P", "routePSnow": 0.0, "routePWall": 1.8, "routePLight": 0.0, "routePAsym": 0.0, "routePSkin": 0.0, "routePHair": 0.0, "routePClarity": 0.55, "routePUnsharp": 55, "routePSeed": 5103}),
            ("alleyP_light_only", {"route": "P", "routePSnow": 0.0, "routePWall": 0.0, "routePLight": 1.4, "routePAsym": 0.0, "routePSkin": 0.0, "routePHair": 0.0, "routePClarity": 0.55, "routePUnsharp": 55, "routePSeed": 5105}),
            ("alleyP_asym_only", {"route": "P", "routePSnow": 0.0, "routePWall": 0.0, "routePLight": 0.0, "routePAsym": 1.4, "routePSkin": 0.0, "routePHair": 0.0, "routePClarity": 0.55, "routePUnsharp": 55, "routePSeed": 5107}),
            ("alleyP_skin_only", {"route": "P", "routePSnow": 0.0, "routePWall": 0.0, "routePLight": 0.0, "routePAsym": 0.0, "routePSkin": 1.8, "routePHair": 0.0, "routePClarity": 0.90, "routePUnsharp": 80, "routePSeed": 5111}),
            ("alleyP_hair_only", {"route": "P", "routePSnow": 0.0, "routePWall": 0.0, "routePLight": 0.0, "routePAsym": 0.0, "routePSkin": 0.0, "routePHair": 2.0, "routePClarity": 0.90, "routePUnsharp": 80, "routePSeed": 5113}),
            ("alleyP_bg_combo", {"route": "P", "routePSnow": 1.4, "routePWall": 1.8, "routePLight": 1.3, "routePAsym": 1.0, "routePSkin": 0.0, "routePHair": 0.0, "routePClarity": 0.65, "routePUnsharp": 65, "routePSeed": 5117}),
            ("alleyP_subject_combo", {"route": "P", "routePSnow": 0.0, "routePWall": 0.0, "routePLight": 0.3, "routePAsym": 0.0, "routePSkin": 1.8, "routePHair": 2.0, "routePClarity": 1.05, "routePUnsharp": 90, "routePSeed": 5119}),
            ("alleyP_balanced", {"route": "P", "routePSnow": 1.0, "routePWall": 1.4, "routePLight": 1.0, "routePAsym": 0.8, "routePSkin": 1.0, "routePHair": 1.2, "routePClarity": 0.75, "routePUnsharp": 70, "routePSeed": 5123}),
            ("alleyP_balanced_strong", {"route": "P", "routePSnow": 1.8, "routePWall": 2.3, "routePLight": 1.6, "routePAsym": 1.2, "routePSkin": 1.5, "routePHair": 1.8, "routePClarity": 0.95, "routePUnsharp": 85, "routePSeed": 5129}),
            ("alleyP_wall_snow_skin", {"route": "P", "routePSnow": 2.0, "routePWall": 2.5, "routePLight": 0.5, "routePAsym": 0.4, "routePSkin": 1.6, "routePHair": 0.8, "routePClarity": 1.0, "routePUnsharp": 90, "routePSeed": 5131}),
            ("alleyP_light_hair_skin", {"route": "P", "routePSnow": 0.8, "routePWall": 0.8, "routePLight": 2.0, "routePAsym": 0.8, "routePSkin": 1.8, "routePHair": 2.2, "routePClarity": 1.1, "routePUnsharp": 95, "routePSeed": 5137}),
            ("alleyP_extreme_bg", {"route": "P", "routePSnow": 2.8, "routePWall": 3.2, "routePLight": 2.4, "routePAsym": 1.8, "routePSkin": 0.4, "routePHair": 0.6, "routePClarity": 0.75, "routePUnsharp": 75, "routePSeed": 5141}),
            ("alleyP_extreme_subject", {"route": "P", "routePSnow": 0.4, "routePWall": 0.5, "routePLight": 1.0, "routePAsym": 0.2, "routePSkin": 2.8, "routePHair": 3.0, "routePClarity": 1.35, "routePUnsharp": 105, "routePSeed": 5143}),
            ("alleyP_extreme_all", {"route": "P", "routePSnow": 3.0, "routePWall": 3.2, "routePLight": 2.5, "routePAsym": 2.0, "routePSkin": 2.4, "routePHair": 3.0, "routePClarity": 1.25, "routePUnsharp": 105, "routePSeed": 5147}),
            ("alleyP_with_double_jpeg", {"route": "P", "routePSnow": 1.8, "routePWall": 2.3, "routePLight": 1.6, "routePAsym": 1.2, "routePSkin": 1.5, "routePHair": 1.8, "routePClarity": 0.95, "routePUnsharp": 85, "routePSeed": 5129, "doubleJpeg": True}),
        ]
        results = []
        for name, patch in variants_p:
            settings = dict(center)
            settings.update(patch)
            settings["writeExif"] = False
            results.append((name, settings))
        return results
        variants_n = [
            ("alleyN_donor_soft", {"route": "N", "routeNFaceResidual": 0.8, "routeNBgResidual": 1.2, "routeNDarkResidual": 1.0, "routeNLowResidual": 0.35, "routeNColorIrregular": 0.35, "routeNSkinTone": 0.35, "routeNCfa": 0.25, "routeNFaceClarity": 0.55, "routeNUnsharp": 45, "routeNSeed": 3101}),
            ("alleyN_donor_balanced", {"route": "N", "routeNFaceResidual": 1.2, "routeNBgResidual": 1.6, "routeNDarkResidual": 1.35, "routeNLowResidual": 0.45, "routeNColorIrregular": 0.55, "routeNSkinTone": 0.55, "routeNCfa": 0.35, "routeNFaceClarity": 0.70, "routeNUnsharp": 60, "routeNSeed": 3107}),
            ("alleyN_donor_strong", {"route": "N", "routeNFaceResidual": 1.6, "routeNBgResidual": 2.0, "routeNDarkResidual": 1.65, "routeNLowResidual": 0.60, "routeNColorIrregular": 0.80, "routeNSkinTone": 0.80, "routeNCfa": 0.48, "routeNFaceClarity": 0.90, "routeNUnsharp": 75, "routeNSeed": 3113}),
            ("alleyN_face_heavy", {"route": "N", "routeNFaceResidual": 2.2, "routeNBgResidual": 1.6, "routeNDarkResidual": 1.35, "routeNLowResidual": 0.50, "routeNColorIrregular": 0.65, "routeNSkinTone": 1.25, "routeNCfa": 0.40, "routeNFaceClarity": 1.10, "routeNUnsharp": 85, "routeNSeed": 3119}),
            ("alleyN_bg_heavy", {"route": "N", "routeNFaceResidual": 1.1, "routeNBgResidual": 2.8, "routeNDarkResidual": 2.2, "routeNLowResidual": 0.90, "routeNColorIrregular": 1.00, "routeNSkinTone": 0.55, "routeNCfa": 0.55, "routeNFaceClarity": 0.80, "routeNUnsharp": 70, "routeNSeed": 3121}),
            ("alleyN_dark_heavy", {"route": "N", "routeNFaceResidual": 1.3, "routeNBgResidual": 1.8, "routeNDarkResidual": 3.0, "routeNLowResidual": 0.70, "routeNColorIrregular": 0.80, "routeNSkinTone": 0.70, "routeNCfa": 0.55, "routeNFaceClarity": 0.85, "routeNUnsharp": 75, "routeNSeed": 3127}),
            ("alleyN_real1", {"route": "N", "routeNFaceResidual": 1.7, "routeNBgResidual": 2.2, "routeNDarkResidual": 1.8, "routeNLowResidual": 0.65, "routeNColorIrregular": 0.80, "routeNSkinTone": 0.95, "routeNCfa": 0.50, "routeNFaceClarity": 0.95, "routeNUnsharp": 80, "routeNSeed": 3131}),
            ("alleyN_real2", {"route": "N", "routeNFaceResidual": 1.7, "routeNBgResidual": 2.2, "routeNDarkResidual": 1.8, "routeNLowResidual": 0.65, "routeNColorIrregular": 0.80, "routeNSkinTone": 0.95, "routeNCfa": 0.50, "routeNFaceClarity": 0.95, "routeNUnsharp": 80, "routeNSeed": 3132}),
            ("alleyN_real3", {"route": "N", "routeNFaceResidual": 1.7, "routeNBgResidual": 2.2, "routeNDarkResidual": 1.8, "routeNLowResidual": 0.65, "routeNColorIrregular": 0.80, "routeNSkinTone": 0.95, "routeNCfa": 0.50, "routeNFaceClarity": 0.95, "routeNUnsharp": 80, "routeNSeed": 3133}),
            ("alleyN_real4", {"route": "N", "routeNFaceResidual": 1.7, "routeNBgResidual": 2.2, "routeNDarkResidual": 1.8, "routeNLowResidual": 0.65, "routeNColorIrregular": 0.80, "routeNSkinTone": 0.95, "routeNCfa": 0.50, "routeNFaceClarity": 0.95, "routeNUnsharp": 80, "routeNSeed": 3134}),
            ("alleyN_real5", {"route": "N", "routeNFaceResidual": 1.7, "routeNBgResidual": 2.2, "routeNDarkResidual": 1.8, "routeNLowResidual": 0.65, "routeNColorIrregular": 0.80, "routeNSkinTone": 0.95, "routeNCfa": 0.50, "routeNFaceClarity": 0.95, "routeNUnsharp": 80, "routeNSeed": 3135}),
            ("alleyN_real6", {"route": "N", "routeNFaceResidual": 1.7, "routeNBgResidual": 2.2, "routeNDarkResidual": 1.8, "routeNLowResidual": 0.65, "routeNColorIrregular": 0.80, "routeNSkinTone": 0.95, "routeNCfa": 0.50, "routeNFaceClarity": 0.95, "routeNUnsharp": 80, "routeNSeed": 3136}),
            ("alleyN_real7", {"route": "N", "routeNFaceResidual": 1.7, "routeNBgResidual": 2.2, "routeNDarkResidual": 1.8, "routeNLowResidual": 0.65, "routeNColorIrregular": 0.80, "routeNSkinTone": 0.95, "routeNCfa": 0.50, "routeNFaceClarity": 0.95, "routeNUnsharp": 80, "routeNSeed": 3137}),
            ("alleyN_real8", {"route": "N", "routeNFaceResidual": 1.7, "routeNBgResidual": 2.2, "routeNDarkResidual": 1.8, "routeNLowResidual": 0.65, "routeNColorIrregular": 0.80, "routeNSkinTone": 0.95, "routeNCfa": 0.50, "routeNFaceClarity": 0.95, "routeNUnsharp": 80, "routeNSeed": 3138}),
            ("alleyN_extreme_visible", {"route": "N", "routeNFaceResidual": 2.8, "routeNBgResidual": 3.5, "routeNDarkResidual": 3.2, "routeNLowResidual": 1.10, "routeNColorIrregular": 1.35, "routeNSkinTone": 1.55, "routeNCfa": 0.85, "routeNFaceClarity": 1.25, "routeNUnsharp": 95, "routeNSeed": 3149}),
            ("alleyN_extreme_double", {"route": "N", "routeNFaceResidual": 2.4, "routeNBgResidual": 3.0, "routeNDarkResidual": 2.6, "routeNLowResidual": 0.90, "routeNColorIrregular": 1.10, "routeNSkinTone": 1.30, "routeNCfa": 0.75, "routeNFaceClarity": 1.20, "routeNUnsharp": 95, "routeNSeed": 3151, "doubleJpeg": True}),
        ]
        results = []
        for name, patch in variants_n:
            settings = dict(center)
            settings.update(patch)
            settings["writeExif"] = False
            results.append((name, settings))
        return results
        variants_m = [
            ("alleyM_soft_sensor", {"route": "M", "routeMShot": 0.010, "routeMRead": 0.0035, "routeMFixed": 0.0012, "routeMCfa": 0.28, "routeMFaceTexture": 0.55, "routeMBgTexture": 0.70, "routeMBlock": 0.50, "routeMFaceClarity": 0.35, "routeMUnsharp": 45, "routeMSeed": 2101}),
            ("alleyM_sensor_tex", {"route": "M", "routeMShot": 0.014, "routeMRead": 0.0045, "routeMFixed": 0.0016, "routeMCfa": 0.38, "routeMFaceTexture": 0.80, "routeMBgTexture": 0.95, "routeMBlock": 0.75, "routeMFaceClarity": 0.45, "routeMUnsharp": 55, "routeMSeed": 2107}),
            ("alleyM_sensor_tex_plus", {"route": "M", "routeMShot": 0.018, "routeMRead": 0.0055, "routeMFixed": 0.0020, "routeMCfa": 0.48, "routeMFaceTexture": 1.05, "routeMBgTexture": 1.20, "routeMBlock": 0.95, "routeMFaceClarity": 0.55, "routeMUnsharp": 65, "routeMSeed": 2111}),
            ("alleyM_bg_heavy_face_clear", {"route": "M", "routeMShot": 0.018, "routeMRead": 0.0050, "routeMFixed": 0.0022, "routeMCfa": 0.55, "routeMFaceTexture": 0.60, "routeMBgTexture": 1.65, "routeMBlock": 1.20, "routeMFaceClarity": 0.65, "routeMUnsharp": 75, "routeMSeed": 2117}),
            ("alleyM_face_texture_strong", {"route": "M", "routeMShot": 0.016, "routeMRead": 0.0048, "routeMFixed": 0.0018, "routeMCfa": 0.42, "routeMFaceTexture": 1.45, "routeMBgTexture": 1.00, "routeMBlock": 0.90, "routeMFaceClarity": 0.85, "routeMUnsharp": 70, "routeMSeed": 2129}),
            ("alleyM_face_texture_max", {"route": "M", "routeMShot": 0.018, "routeMRead": 0.0058, "routeMFixed": 0.0022, "routeMCfa": 0.50, "routeMFaceTexture": 1.85, "routeMBgTexture": 1.15, "routeMBlock": 1.00, "routeMFaceClarity": 1.05, "routeMUnsharp": 80, "routeMSeed": 2131}),
            ("alleyM_dct_bg", {"route": "M", "routeMShot": 0.013, "routeMRead": 0.0042, "routeMFixed": 0.0015, "routeMCfa": 0.34, "routeMFaceTexture": 0.75, "routeMBgTexture": 1.10, "routeMBlock": 1.75, "routeMBlockSize": 8, "routeMFaceClarity": 0.55, "routeMUnsharp": 65, "routeMSeed": 2137}),
            ("alleyM_dct_bg16", {"route": "M", "routeMShot": 0.013, "routeMRead": 0.0042, "routeMFixed": 0.0015, "routeMCfa": 0.34, "routeMFaceTexture": 0.75, "routeMBgTexture": 1.10, "routeMBlock": 1.75, "routeMBlockSize": 16, "routeMFaceClarity": 0.55, "routeMUnsharp": 65, "routeMSeed": 2141}),
            ("alleyM_low_cfa_high_skin", {"route": "M", "routeMShot": 0.018, "routeMRead": 0.0060, "routeMFixed": 0.0024, "routeMCfa": 0.20, "routeMFaceTexture": 1.75, "routeMBgTexture": 1.35, "routeMBlock": 1.10, "routeMFaceClarity": 1.05, "routeMUnsharp": 85, "routeMSeed": 2143}),
            ("alleyM_high_cfa_mid_skin", {"route": "M", "routeMShot": 0.016, "routeMRead": 0.0050, "routeMFixed": 0.0020, "routeMCfa": 0.75, "routeMFaceTexture": 1.10, "routeMBgTexture": 1.50, "routeMBlock": 1.25, "routeMFaceClarity": 0.80, "routeMUnsharp": 80, "routeMSeed": 2147}),
            ("alleyM_face_oval_wide", {"route": "M", "routeMFaceRx": 0.23, "routeMFaceRy": 0.20, "routeMFaceOval": 1.10, "routeMShot": 0.016, "routeMRead": 0.0050, "routeMFixed": 0.0020, "routeMCfa": 0.42, "routeMFaceTexture": 1.35, "routeMBgTexture": 1.20, "routeMBlock": 1.00, "routeMFaceClarity": 0.90, "routeMUnsharp": 75, "routeMSeed": 2153}),
            ("alleyM_face_oval_tight", {"route": "M", "routeMFaceRx": 0.16, "routeMFaceRy": 0.15, "routeMFaceOval": 1.05, "routeMShot": 0.018, "routeMRead": 0.0055, "routeMFixed": 0.0020, "routeMCfa": 0.48, "routeMFaceTexture": 1.60, "routeMBgTexture": 1.30, "routeMBlock": 1.10, "routeMFaceClarity": 1.10, "routeMUnsharp": 85, "routeMSeed": 2159}),
            ("alleyM_double_jpeg", {"route": "M", "routeMShot": 0.016, "routeMRead": 0.0050, "routeMFixed": 0.0020, "routeMCfa": 0.42, "routeMFaceTexture": 1.20, "routeMBgTexture": 1.30, "routeMBlock": 1.20, "routeMFaceClarity": 0.85, "routeMUnsharp": 80, "routeMSeed": 2161, "doubleJpeg": True}),
            ("alleyM_extreme_no_geometry", {"route": "M", "routeMShot": 0.024, "routeMRead": 0.0075, "routeMFixed": 0.0030, "routeMCfa": 0.80, "routeMFaceTexture": 2.10, "routeMBgTexture": 1.85, "routeMBlock": 1.60, "routeMFaceClarity": 1.20, "routeMUnsharp": 95, "routeMSeed": 2167}),
        ]
        results = []
        for name, patch in variants_m:
            settings = dict(center)
            settings.update(patch)
            settings["writeExif"] = False
            results.append((name, settings))
        return results
        variants = [
            ("alleyL_anchor_blur_bad", {"route": "L", "routeLCropLeft": 18.0, "routeLCropRight": 4.0, "routeLCropTop": 2.0, "routeLCropBottom": 4.0, "routeLLongEdge": 720, "routeLQuilt": 0.45, "routeLBlock": 16, "routeLBlockShift": 4.0, "routeLTone": 2.0, "routeLUnsharp": 130, "routeLSeed": 1601}),
            ("alleyL_face_clear_tex02", {"route": "L", "routeLCropLeft": 18.0, "routeLCropRight": 4.0, "routeLCropTop": 2.0, "routeLCropBottom": 4.0, "routeLLongEdge": 720, "routeLQuilt": 0.45, "routeLBlock": 16, "routeLBlockShift": 4.0, "routeLTone": 2.0, "routeLUnsharp": 130, "routeLFaceProtect": 0.98, "routeLFaceOval": 1.15, "routeLFaceFeather": 4.0, "routeLFaceTexture": 0.20, "routeLFaceClarity": 0.30, "routeLSeed": 1601}),
            ("alleyL_face_clear_tex04", {"route": "L", "routeLCropLeft": 18.0, "routeLCropRight": 4.0, "routeLCropTop": 2.0, "routeLCropBottom": 4.0, "routeLLongEdge": 720, "routeLQuilt": 0.45, "routeLBlock": 16, "routeLBlockShift": 4.0, "routeLTone": 2.0, "routeLUnsharp": 130, "routeLFaceProtect": 0.98, "routeLFaceOval": 1.15, "routeLFaceFeather": 4.0, "routeLFaceTexture": 0.40, "routeLFaceClarity": 0.35, "routeLSeed": 1601}),
            ("alleyL_face_clear_tex06", {"route": "L", "routeLCropLeft": 18.0, "routeLCropRight": 4.0, "routeLCropTop": 2.0, "routeLCropBottom": 4.0, "routeLLongEdge": 720, "routeLQuilt": 0.45, "routeLBlock": 16, "routeLBlockShift": 4.0, "routeLTone": 2.0, "routeLUnsharp": 130, "routeLFaceProtect": 0.98, "routeLFaceOval": 1.15, "routeLFaceFeather": 4.0, "routeLFaceTexture": 0.60, "routeLFaceClarity": 0.40, "routeLSeed": 1601}),
            ("alleyL_face_clear_crop14_tex04", {"route": "L", "routeLCropLeft": 14.0, "routeLCropRight": 3.0, "routeLCropTop": 1.5, "routeLCropBottom": 3.0, "routeLLongEdge": 720, "routeLQuilt": 0.45, "routeLBlock": 16, "routeLBlockShift": 4.0, "routeLTone": 2.0, "routeLUnsharp": 130, "routeLFaceProtect": 0.98, "routeLFaceOval": 1.15, "routeLFaceFeather": 4.0, "routeLFaceTexture": 0.40, "routeLFaceClarity": 0.35, "routeLSeed": 1601}),
            ("alleyL_face_clear_shift2_tex04", {"route": "L", "routeLCropLeft": 18.0, "routeLCropRight": 4.0, "routeLCropTop": 2.0, "routeLCropBottom": 4.0, "routeLLongEdge": 720, "routeLQuilt": 0.45, "routeLBlock": 16, "routeLBlockShift": 2.0, "routeLTone": 2.0, "routeLUnsharp": 130, "routeLFaceProtect": 0.98, "routeLFaceOval": 1.15, "routeLFaceFeather": 4.0, "routeLFaceTexture": 0.40, "routeLFaceClarity": 0.35, "routeLSeed": 1601}),
            ("alleyL_face_clear_quilt32_tex04", {"route": "L", "routeLCropLeft": 18.0, "routeLCropRight": 4.0, "routeLCropTop": 2.0, "routeLCropBottom": 4.0, "routeLLongEdge": 720, "routeLQuilt": 0.32, "routeLBlock": 20, "routeLBlockShift": 4.0, "routeLTone": 2.0, "routeLUnsharp": 130, "routeLFaceProtect": 0.98, "routeLFaceOval": 1.15, "routeLFaceFeather": 4.0, "routeLFaceTexture": 0.40, "routeLFaceClarity": 0.35, "routeLSeed": 1601}),
            ("alleyL_face_clear_tex04_double", {"route": "L", "routeLCropLeft": 18.0, "routeLCropRight": 4.0, "routeLCropTop": 2.0, "routeLCropBottom": 4.0, "routeLLongEdge": 720, "routeLQuilt": 0.45, "routeLBlock": 16, "routeLBlockShift": 4.0, "routeLTone": 2.0, "routeLUnsharp": 130, "routeLFaceProtect": 0.98, "routeLFaceOval": 1.15, "routeLFaceFeather": 4.0, "routeLFaceTexture": 0.40, "routeLFaceClarity": 0.35, "routeLSeed": 1601, "doubleJpeg": True}),
            ("alleyL_face_mid_tex08", {"route": "L", "routeLCropLeft": 18.0, "routeLCropRight": 4.0, "routeLCropTop": 2.0, "routeLCropBottom": 4.0, "routeLLongEdge": 720, "routeLQuilt": 0.45, "routeLBlock": 16, "routeLBlockShift": 4.0, "routeLTone": 2.0, "routeLUnsharp": 145, "routeLFaceProtect": 0.72, "routeLFaceOval": 1.00, "routeLFaceFeather": 4.0, "routeLFaceTexture": 0.80, "routeLFaceClarity": 0.60, "routeLSeed": 1601}),
            ("alleyL_face_mid_tex10", {"route": "L", "routeLCropLeft": 18.0, "routeLCropRight": 4.0, "routeLCropTop": 2.0, "routeLCropBottom": 4.0, "routeLLongEdge": 720, "routeLQuilt": 0.45, "routeLBlock": 16, "routeLBlockShift": 4.0, "routeLTone": 2.0, "routeLUnsharp": 150, "routeLFaceProtect": 0.62, "routeLFaceOval": 0.95, "routeLFaceFeather": 3.0, "routeLFaceTexture": 1.00, "routeLFaceClarity": 0.80, "routeLSeed": 1601}),
            ("alleyL_face_mid_crop14_tex10", {"route": "L", "routeLCropLeft": 14.0, "routeLCropRight": 3.0, "routeLCropTop": 1.5, "routeLCropBottom": 3.0, "routeLLongEdge": 720, "routeLQuilt": 0.45, "routeLBlock": 16, "routeLBlockShift": 4.0, "routeLTone": 2.0, "routeLUnsharp": 150, "routeLFaceProtect": 0.62, "routeLFaceOval": 0.95, "routeLFaceFeather": 3.0, "routeLFaceTexture": 1.00, "routeLFaceClarity": 0.80, "routeLSeed": 1601}),
            ("alleyL_face_mid_shift2_tex10", {"route": "L", "routeLCropLeft": 18.0, "routeLCropRight": 4.0, "routeLCropTop": 2.0, "routeLCropBottom": 4.0, "routeLLongEdge": 720, "routeLQuilt": 0.45, "routeLBlock": 16, "routeLBlockShift": 2.0, "routeLTone": 2.0, "routeLUnsharp": 150, "routeLFaceProtect": 0.62, "routeLFaceOval": 0.95, "routeLFaceFeather": 3.0, "routeLFaceTexture": 1.00, "routeLFaceClarity": 0.80, "routeLSeed": 1601}),
            ("alleyL_anchor_lessblur", {"route": "L", "routeLCropLeft": 18.0, "routeLCropRight": 4.0, "routeLCropTop": 2.0, "routeLCropBottom": 4.0, "routeLLongEdge": 840, "routeLQuilt": 0.45, "routeLBlock": 16, "routeLBlockShift": 4.0, "routeLTone": 2.0, "routeLUnsharp": 150, "routeLFaceProtect": 0.45, "routeLFaceTexture": 0.80, "routeLFaceClarity": 0.80, "routeLSeed": 1601}),
        ]
        results = []
        for name, patch in variants:
            settings = dict(center)
            settings.update(patch)
            settings["writeExif"] = False
            results.append((name, settings))
        return results
    if reason == "bridge_like_camera_residual":
        center = dict(auto)
        center.pop("autoProfile", None)
        variants = [
            ("bridgeA_auto_luma18", {}),
            ("bridgeA_luma16", {"route": "A", "lumaNoise": 16, "chromaScale": 1.2, "residualScale": 1.0, "resample": 0, "doubleJpeg": False}),
            ("bridgeA_luma20", {"route": "A", "lumaNoise": 20, "chromaScale": 1.2, "residualScale": 1.0, "resample": 0, "doubleJpeg": False}),
            ("bridgeA_luma22", {"route": "A", "lumaNoise": 22, "chromaScale": 1.2, "residualScale": 1.0, "resample": 0, "doubleJpeg": False}),
            ("bridgeA_low_chroma", {"route": "A", "lumaNoise": 18, "chromaScale": 0.9, "residualScale": 1.0, "resample": 0, "doubleJpeg": False}),
            ("bridgeA_high_chroma", {"route": "A", "lumaNoise": 18, "chromaScale": 1.5, "residualScale": 1.0, "resample": 0, "doubleJpeg": False}),
            ("bridgeA_residual08", {"route": "A", "lumaNoise": 18, "chromaScale": 1.2, "residualScale": 0.8, "resample": 0, "doubleJpeg": False}),
            ("bridgeA_residual12", {"route": "A", "lumaNoise": 18, "chromaScale": 1.2, "residualScale": 1.2, "resample": 0, "doubleJpeg": False}),
            ("bridgeE_balanced_check", {"route": "E", "routeEShotNoise": 0.020, "routeEReadNoise": 0.0060, "routeEFixedNoise": 0.0025, "routeEDenoise": 0.55, "routeESharpen": 0.10, "routeECcm": 0.055, "routeEResample": 4, "routeESeed": 509}),
            ("bridgeC_quality_check", {"route": "C", "routeCDenoise": 1.55, "routeCEdgeProtect": 2.07, "routeCHighKeep": 0.150, "routeCMidKeep": 0.44, "routeCChroma": 0.24, "routeCResidualFloor": 0.05, "routeCBlock": 0.10, "routeCResample": 4}),
        ]
        results = []
        for name, patch in variants:
            settings = dict(center)
            settings.update(patch)
            settings["writeExif"] = False
            results.append((name, settings))
        return results
    if reason != "ultra_smooth_low_residual_surface":
        return generic_candidate_settings(base)

    center = dict(auto)
    center.pop("autoProfile", None)
    variants = [
        ("auto_current_center", {}),
        ("e203_c024_h150", {"routeCDenoise": 1.55, "routeCEdgeProtect": 2.03, "routeCHighKeep": 0.150, "routeCMidKeep": 0.44, "routeCChroma": 0.24, "routeCResidualFloor": 0.05, "routeCBlock": 0.10, "routeCResample": 4}),
        ("e205_c024_h150", {"routeCDenoise": 1.55, "routeCEdgeProtect": 2.05, "routeCHighKeep": 0.150, "routeCMidKeep": 0.44, "routeCChroma": 0.24, "routeCResidualFloor": 0.05, "routeCBlock": 0.10, "routeCResample": 4}),
        ("e207_c024_h150", {"routeCDenoise": 1.55, "routeCEdgeProtect": 2.07, "routeCHighKeep": 0.150, "routeCMidKeep": 0.44, "routeCChroma": 0.24, "routeCResidualFloor": 0.05, "routeCBlock": 0.10, "routeCResample": 4}),
        ("e210_c024_h150", {"routeCDenoise": 1.55, "routeCEdgeProtect": 2.10, "routeCHighKeep": 0.150, "routeCMidKeep": 0.44, "routeCChroma": 0.24, "routeCResidualFloor": 0.05, "routeCBlock": 0.10, "routeCResample": 4}),
        ("e205_c026_h150", {"routeCDenoise": 1.55, "routeCEdgeProtect": 2.05, "routeCHighKeep": 0.150, "routeCMidKeep": 0.44, "routeCChroma": 0.26, "routeCResidualFloor": 0.05, "routeCBlock": 0.10, "routeCResample": 4}),
        ("e205_c028_h150", {"routeCDenoise": 1.55, "routeCEdgeProtect": 2.05, "routeCHighKeep": 0.150, "routeCMidKeep": 0.44, "routeCChroma": 0.28, "routeCResidualFloor": 0.05, "routeCBlock": 0.10, "routeCResample": 4}),
        ("e205_c030_h150", {"routeCDenoise": 1.55, "routeCEdgeProtect": 2.05, "routeCHighKeep": 0.150, "routeCMidKeep": 0.44, "routeCChroma": 0.30, "routeCResidualFloor": 0.05, "routeCBlock": 0.10, "routeCResample": 4}),
        ("e205_h145_c024", {"routeCDenoise": 1.55, "routeCEdgeProtect": 2.05, "routeCHighKeep": 0.145, "routeCMidKeep": 0.44, "routeCChroma": 0.24, "routeCResidualFloor": 0.05, "routeCBlock": 0.10, "routeCResample": 4}),
        ("e205_h148_c024", {"routeCDenoise": 1.55, "routeCEdgeProtect": 2.05, "routeCHighKeep": 0.148, "routeCMidKeep": 0.44, "routeCChroma": 0.24, "routeCResidualFloor": 0.05, "routeCBlock": 0.10, "routeCResample": 4}),
        ("e205_h152_c024", {"routeCDenoise": 1.55, "routeCEdgeProtect": 2.05, "routeCHighKeep": 0.152, "routeCMidKeep": 0.44, "routeCChroma": 0.24, "routeCResidualFloor": 0.05, "routeCBlock": 0.10, "routeCResample": 4}),
        ("e205_r0045_c024", {"routeCDenoise": 1.55, "routeCEdgeProtect": 2.05, "routeCHighKeep": 0.150, "routeCMidKeep": 0.44, "routeCChroma": 0.24, "routeCResidualFloor": 0.045, "routeCBlock": 0.09, "routeCResample": 4}),
        ("e205_r0055_c024", {"routeCDenoise": 1.55, "routeCEdgeProtect": 2.05, "routeCHighKeep": 0.150, "routeCMidKeep": 0.44, "routeCChroma": 0.24, "routeCResidualFloor": 0.055, "routeCBlock": 0.11, "routeCResample": 4}),
        ("e205_d152_c024", {"routeCDenoise": 1.52, "routeCEdgeProtect": 2.05, "routeCHighKeep": 0.150, "routeCMidKeep": 0.44, "routeCChroma": 0.24, "routeCResidualFloor": 0.05, "routeCBlock": 0.10, "routeCResample": 4}),
        ("e205_d158_c024", {"routeCDenoise": 1.58, "routeCEdgeProtect": 2.05, "routeCHighKeep": 0.150, "routeCMidKeep": 0.44, "routeCChroma": 0.24, "routeCResidualFloor": 0.05, "routeCBlock": 0.10, "routeCResample": 4}),
        ("e205_m042_c024", {"routeCDenoise": 1.55, "routeCEdgeProtect": 2.05, "routeCHighKeep": 0.150, "routeCMidKeep": 0.42, "routeCChroma": 0.24, "routeCResidualFloor": 0.05, "routeCBlock": 0.10, "routeCResample": 4}),
        ("e205_m046_c024", {"routeCDenoise": 1.55, "routeCEdgeProtect": 2.05, "routeCHighKeep": 0.150, "routeCMidKeep": 0.46, "routeCChroma": 0.24, "routeCResidualFloor": 0.05, "routeCBlock": 0.10, "routeCResample": 4}),
        ("combo_e203_h148_c026", {"routeCDenoise": 1.55, "routeCEdgeProtect": 2.03, "routeCHighKeep": 0.148, "routeCMidKeep": 0.44, "routeCChroma": 0.26, "routeCResidualFloor": 0.05, "routeCBlock": 0.10, "routeCResample": 4}),
        ("combo_e205_h148_c026", {"routeCDenoise": 1.55, "routeCEdgeProtect": 2.05, "routeCHighKeep": 0.148, "routeCMidKeep": 0.44, "routeCChroma": 0.26, "routeCResidualFloor": 0.05, "routeCBlock": 0.10, "routeCResample": 4}),
        ("combo_e207_h148_c026", {"routeCDenoise": 1.55, "routeCEdgeProtect": 2.07, "routeCHighKeep": 0.148, "routeCMidKeep": 0.44, "routeCChroma": 0.26, "routeCResidualFloor": 0.05, "routeCBlock": 0.10, "routeCResample": 4}),
        ("combo_e205_h150_c026_r0045", {"routeCDenoise": 1.55, "routeCEdgeProtect": 2.05, "routeCHighKeep": 0.150, "routeCMidKeep": 0.44, "routeCChroma": 0.26, "routeCResidualFloor": 0.045, "routeCBlock": 0.09, "routeCResample": 4}),
        ("combo_e205_h150_c028_r0045", {"routeCDenoise": 1.55, "routeCEdgeProtect": 2.05, "routeCHighKeep": 0.150, "routeCMidKeep": 0.44, "routeCChroma": 0.28, "routeCResidualFloor": 0.045, "routeCBlock": 0.09, "routeCResample": 4}),
        ("combo_e205_h150_c026_d152", {"routeCDenoise": 1.52, "routeCEdgeProtect": 2.05, "routeCHighKeep": 0.150, "routeCMidKeep": 0.44, "routeCChroma": 0.26, "routeCResidualFloor": 0.05, "routeCBlock": 0.10, "routeCResample": 4}),
        ("combo_e205_h150_c026_d158", {"routeCDenoise": 1.58, "routeCEdgeProtect": 2.05, "routeCHighKeep": 0.150, "routeCMidKeep": 0.44, "routeCChroma": 0.26, "routeCResidualFloor": 0.05, "routeCBlock": 0.10, "routeCResample": 4}),
        ("double_e205_h150_c026", {"routeCDenoise": 1.55, "routeCEdgeProtect": 2.05, "routeCHighKeep": 0.150, "routeCMidKeep": 0.44, "routeCChroma": 0.26, "routeCResidualFloor": 0.05, "routeCBlock": 0.10, "routeCResample": 4, "doubleJpeg": True}),
        ("combo_best_round6", {"routeCDenoise": 1.55, "routeCEdgeProtect": 2.05, "routeCHighKeep": 0.150, "routeCMidKeep": 0.44, "routeCBackgroundDark": 5.8, "routeCResidualFloor": 0.045, "routeCBlock": 0.09, "routeCChroma": 0.26, "routeCResample": 4}),
        ("routeE_pseudo_raw_soft", {"route": "E", "routeEShotNoise": 0.014, "routeEReadNoise": 0.0045, "routeEFixedNoise": 0.0018, "routeEDenoise": 0.50, "routeESharpen": 0.08, "routeECcm": 0.040, "routeEResample": 3, "routeESeed": 503}),
        ("routeE_pseudo_raw_balanced", {"route": "E", "routeEShotNoise": 0.020, "routeEReadNoise": 0.0060, "routeEFixedNoise": 0.0025, "routeEDenoise": 0.55, "routeESharpen": 0.10, "routeECcm": 0.055, "routeEResample": 4, "routeESeed": 509}),
        ("routeE_pseudo_raw_dark", {"route": "E", "routeEShotNoise": 0.026, "routeEReadNoise": 0.0080, "routeEFixedNoise": 0.0030, "routeEDenoise": 0.65, "routeESharpen": 0.07, "routeEToe": 0.026, "routeECcm": 0.055, "routeEResample": 4, "routeESeed": 521}),
        ("routeE_pseudo_raw_phone", {"route": "E", "routeEShotNoise": 0.018, "routeEReadNoise": 0.0055, "routeEFixedNoise": 0.0022, "routeEDenoise": 0.85, "routeESharpen": 0.16, "routeECcm": 0.075, "routeEInvWbR": 1.05, "routeEInvWbB": 0.96, "routeEResample": 5, "routeESeed": 541}),
        ("routeE_pseudo_raw_double", {"route": "E", "routeEShotNoise": 0.022, "routeEReadNoise": 0.0065, "routeEFixedNoise": 0.0026, "routeEDenoise": 0.55, "routeESharpen": 0.11, "routeECcm": 0.055, "routeEResample": 4, "doubleJpeg": True, "routeESeed": 557}),
    ]
    results = []
    for name, patch in variants:
        settings = dict(center)
        settings.update(patch)
        settings["route"] = settings.get("route", "C")
        settings["writeExif"] = False
        results.append((name, settings))
    return results


class Handler(SimpleHTTPRequestHandler):
    def end_headers(self):
        self.send_header("Cache-Control", "no-store, max-age=0")
        self.send_header("Pragma", "no-cache")
        super().end_headers()

    def translate_path(self, path):
        parsed = urlparse(path)
        clean = parsed.path.lstrip("/") or "index.html"
        return str((ROOT / clean).resolve())

    def do_POST(self):
        endpoint = urlparse(self.path).path
        if endpoint not in {"/process", "/candidates", "/forensics"}:
            self.send_error(404)
            return
        length = int(self.headers.get("Content-Length", "0"))
        payload = json.loads(self.rfile.read(length).decode("utf-8"))
        if endpoint == "/forensics":
            body = self.handle_forensics(payload)
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return

        data_url = payload["image"]
        raw = data_url.split(",", 1)[1] if "," in data_url else data_url
        image = Image.open(io.BytesIO(base64.b64decode(raw)))
        settings = payload.get("settings", {})

        if endpoint == "/candidates":
            zip_buf = io.BytesIO()
            manifest = []
            profile_settings = auto_route_settings(image, {"route": "auto", "autoRoute": True, "writeExif": False})
            with zipfile.ZipFile(zip_buf, "w", compression=zipfile.ZIP_DEFLATED) as zf:
                for idx, (name, variant) in enumerate(adaptive_candidate_settings(image, settings), start=1):
                    output = process(image, variant)
                    data = save_jpeg_bytes(output, variant)
                    filename = f"{idx:02d}_{name}.jpg"
                    zf.writestr(filename, data)
                    manifest.append({"file": filename, "settings": variant, "bytes": len(data)})
                zf.writestr("manifest.json", json.dumps(manifest, ensure_ascii=False, indent=2))
                zf.writestr(
                    "README.txt",
                    "Upload the candidate JPG files to TruthScan. Report the lowest file name and score back to Codex.\n"
                    f"Auto route: {profile_settings.get('route')} / {profile_settings.get('autoReason')}\n",
                )
                zf.writestr("auto_profile.json", json.dumps(profile_settings, ensure_ascii=False, indent=2))
            encoded = base64.b64encode(zip_buf.getvalue()).decode("ascii")
            body = json.dumps({"archive": f"data:application/zip;base64,{encoded}"}).encode("utf-8")
        else:
            resolved_settings = resolve_settings(image, settings)
            output = process(image, resolved_settings)
            data = save_jpeg_bytes(output, resolved_settings)
            encoded = base64.b64encode(data).decode("ascii")
            response = {
                "image": f"data:image/jpeg;base64,{encoded}",
                "route": resolved_settings.get("route"),
                "autoReason": resolved_settings.get("autoReason"),
                "autoChannel": resolved_settings.get("autoChannel"),
                "autoDecision": resolved_settings.get("autoDecision"),
            }
            body = json.dumps(response, ensure_ascii=False).encode("utf-8")

        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def handle_forensics(self, payload):
        def parse_upload(data_url, fallback_ext):
            header, raw = data_url.split(",", 1) if "," in data_url else ("", data_url)
            data = base64.b64decode(raw)
            mime = header.split(";")[0].replace("data:", "")
            ext = {
                "image/jpeg": ".jpg",
                "image/jpg": ".jpg",
                "image/png": ".png",
                "image/webp": ".webp",
            }.get(mime, fallback_ext)
            return data, ext

        run_id = uuid.uuid4().hex[:12]
        out_dir = ROOT / "analysis_outputs" / "web_forensics" / run_id
        out_dir.mkdir(parents=True, exist_ok=True)
        source_bytes, source_ext = parse_upload(payload["source"], ".png")
        suspect_bytes, suspect_ext = parse_upload(payload["suspect"], ".jpg")
        source_path = out_dir / f"source{source_ext}"
        suspect_path = out_dir / f"suspect{suspect_ext}"
        source_path.write_bytes(source_bytes)
        suspect_path.write_bytes(suspect_bytes)
        report = analyze_forensics_pair(source_path, suspect_path, out_dir)

        heatmaps = {}
        for name, path in report.get("heatmaps", {}).items():
            p = Path(path)
            if p.exists():
                encoded = base64.b64encode(p.read_bytes()).decode("ascii")
                heatmaps[name] = f"data:image/png;base64,{encoded}"
        report["heatmap_data_urls"] = heatmaps
        report["run_id"] = run_id
        return json.dumps(report, ensure_ascii=False).encode("utf-8")


if __name__ == "__main__":
    mimetypes.add_type("text/javascript", ".js")
    server = ThreadingHTTPServer(("127.0.0.1", 8765), Handler)
    print("Image Texture Lab running at http://127.0.0.1:8765/")
    server.serve_forever()
