# Defensive Forensics Report

Risk score: **100 / 100**

## Defensive Flags

- `global_channel_affine_darkening`
- `broad_high_frequency_residual_suppression`
- `jpeg_blockiness_increase`
- `high_correlation_but_widespread_low_amplitude_changes`
- `known_phlegethon_quant_table_sums`
- `known_phlegethon_luma_first8`
- `known_phlegethon_chroma_first8`
- `jfif_without_exif`

## Pair Metrics

- Mean RGB shift: `[-3.4631, -2.9344, -2.7577]`
- Mean absolute RGB delta: `[4.2779, 3.6505, 3.9329]`
- Changed pixels > 3: `0.586591`
- Changed pixels > 10: `0.120911`
- Residual std source/suspect: `2.2408` / `1.8843`
- Laplacian std source/suspect: `8.9632` / `7.5372`
- Blockiness source/suspect: `1.6456` / `1.9439`

## Channel Fit

| Channel | Gain | Offset | Correlation |
|---|---:|---:|---:|
| R | 0.967461 | -1.668849 | 0.997931 |
| G | 0.970711 | -1.374864 | 0.99887 |
| B | 0.970294 | -1.336976 | 0.998061 |

## JPEG Fingerprint

```json
{
  "layers": 3,
  "layer": [
    [
      1,
      2,
      2,
      0
    ],
    [
      2,
      1,
      1,
      1
    ],
    [
      3,
      1,
      1,
      1
    ]
  ],
  "qtables": {
    "0": {
      "sum": 592,
      "first8": [
        3,
        2,
        2,
        3,
        4,
        6,
        8,
        10
      ]
    },
    "1": {
      "sum": 891,
      "first8": [
        3,
        3,
        4,
        8,
        16,
        16,
        16,
        16
      ]
    }
  }
}
```

## Heatmaps

- abs_diff_x8: `analysis_outputs\defensive_forensics_a19\abs_diff_x8.png`
- signed_luma_diff: `analysis_outputs\defensive_forensics_a19\signed_luma_diff_red_brighter_blue_darker.png`