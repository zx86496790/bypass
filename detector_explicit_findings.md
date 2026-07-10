# Detector Explicit Findings

This file records explicit detector explanations, visible heatmap focus, and black-box conclusions that can guide future tests.

## 2026-06-06 - Alley Snow Portrait

Input reference:

- `C:/Users/zsen/Desktop/Gemini_Generated_Image_wxk0h6wxk0h6wxk0.png`

Detector explanation provided by user:

```text
Detailed Reasoning
The image exhibits several characteristics typical of AI-generated content, including perfect symmetry in the composition and unnatural lighting consistency. The snowflakes appear to be falling uniformly, which is often difficult to achieve in natural photography. The texture of the brick wall is highly detailed but appears artificial upon close inspection. These factors combined suggest a high likelihood of AI generation.

Key Indicators
overly perfect symmetry in the alleyway composition
unnatural lighting consistency
synthetic snowflakes falling uniformly
highly detailed texture on the brick wall that appears artificial
slightly unnatural pose of the subject

Visual Patterns
hyper-realistic rendering style
overly perfect symmetry
synthetic lighting characteristics
compositional AI generation signatures
```

Heatmap focus observed:

- Strong focus on subject face, hair, scarf, and upper body.
- Strong focus on right brick wall texture.
- Strong focus on alley depth/composition.
- Some focus on snow/dark ground regions.
- The heatmap did not look like a pure hidden-watermark visualization. It looked like semantic/visual attribution.

Explicit detector claims to target:

- Alleyway composition is too symmetric or too clean.
- Lighting consistency is unnatural.
- Snowflakes are too uniform.
- Brick wall texture is highly detailed but artificial.
- Subject pose is slightly unnatural.
- Overall style is hyper-realistic.
- There are compositional AI generation signatures.

Black-box results connected to these claims:

- Low-level camera simulation routes did not work reliably on this image class.
- `Route M` no-geometry sensor/CFA/DCT/skin microtexture: all 97%.
- `Route N` real-photo donor residual transfer: all 97%.
- The only sub-30 result was an old blurry/low-resolution `Route L` anchor, but the face became unacceptable.
- When face clarity was restored, scores rebounded.

Interpretation:

- The detector is likely not relying only on JPEG noise, sensor noise, CFA traces, or real-photo residuals.
- For this image, the important signal appears to be higher-level visual/semantic structure:
  subject/face distribution, brick wall texture, snow distribution, lighting, and composition.
- A successful clear-image route must alter these visible factors rather than only adding camera noise.

Implemented response:

- Added `Route P` as a semantic artifact reducer.
- `Route P` targets:
  snow irregularity, brick wall irregularity, lighting inconsistency, slight background asymmetry, skin micro-irregularity, and hair/dark-cloth texture.
- Candidate pack includes single-factor probes:
  snow only, wall only, light only, asymmetry only, skin only, hair only.
- Candidate pack also includes mixed and extreme combinations.

Open question:

- If `Route P` stays near 97, the detector explanation may be descriptive rather than causal, or the decisive signal may be deeper subject/model fingerprint features that are not removable with ordinary post-processing.

## 2026-06-06 - OpenAI / SynthID Watermark Claim

Claim discussed:

- A social post claimed that GPT Image 2 and Gemini images have invisible watermarks injected into pixels.
- It also claimed they are immune to screenshot, crop, and high-loss compression.

Assessment:

- Partly true: OpenAI and Google do use provenance and invisible watermarking systems such as C2PA metadata and SynthID-style pixel-level signals for generated images.
- Overstated: official wording is robustness through some edits, not immunity to all screenshots, crops, and high-loss compression.
- The provided visualization is not enough to prove a complete watermark extraction or decoder-level reverse engineering.

Relevance to current testing:

- TruthScan scores and explanations should not automatically be interpreted as direct watermark reads.
- The explanation text and heatmap look more like visual/semantic attribution than a raw SynthID extraction.
- However, watermark/provenance signals may still be one component in some detectors.

