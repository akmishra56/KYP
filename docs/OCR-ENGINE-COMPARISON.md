# OCR candidate diagnostic

RapidOCR 3.10.0 with ONNX Runtime 1.31.0 was installed under ignored backend/data/ocr-evaluation-env. Production Python/mobile dependencies were not replaced. Optional engine pins are in backend/ocr-evaluation-requirements.txt; the initial evaluated transitive dependency freeze is kept locally in backend/data/ocr-evaluation-lock.txt. Source/model licensing still needs release review.

Both supplied Maggi photos were compared as full images and tightly cropped ingredient panels, with 3x crop resampling. RapidOCR ran locally; the current Tesseract WASM engine was called only through the local API with image-processing consent. Temporary crop files were removed. Raw diagnostic results remain local in backend/data/maggi-engine-comparison.json. Repeat with `python -B tools/compare_maggi_ocr.py` from backend (API running, isolated environment installed).

On the sharper crop, RapidOCR extracted most of the readable ingredient panel: nested spices, dehydrated onion/dried garlic, extracts, salt/sugar/starch, additive categories and palm oil. It still misread letters (for example iodized/lodized and substance/subsfance). Full-photo output mixes manufacturer/contact text with ingredients. The original blurred crop still has omissions, ordering and spelling errors. Tesseract produced broken/truncated text and bracket warnings on these diagnostic crops.

This is a useful candidate, not measured real-world accuracy: two photographs of one product, manually chosen crop, no independently reviewed complete transcription. No precision/recall percentage or production replacement is claimed. The app still requires correction and confirmation. The default remains the existing engine; explicit `KYP_OCR_ENGINE=rapidocr` selects the candidate only when its dependencies/models are installed in the API environment. `auto`, `tesseract` and `tesseractjs` are also supported. Candidate orientation delegates to the existing conservative Tesseract orientation helper.

## Real-label comparison

Copy validation/ocr-corpus.example.json into a private corpus folder, replace placeholders with real permission/reviewer/product metadata and reviewed ingredient leaves, and set is_real truthfully. Include food/cosmetics, small text, glare and curved packaging. Images must live inside that folder; exact duplicates and product leakage across baseline/held_out splits are rejected. Native results may be recorded explicitly under recorded_ocr.native; their inference time is not measured by the offline parser.

From backend, in an evaluation environment:

```powershell
python -B -m kyp.evaluate_ocr PATH_TO_MANIFEST --engines tesseractjs,rapidocr,native-recorded
```

At least 30 real images and targets agreed after baseline but before held-out evaluation are still required. The report does not save images or raw label text. Full-photo/crop selection must be decided consistently before comparing held-out engines.

## Match calibration

validation/match-calibration.example.json documents the separate phrase-level evidence. The offline `python -B -m kyp.calibration SAMPLES.json` experiment requires 100 baseline/30 held-out candidates per context, both successes and failures, permitted real examples and separate products. It reports Brier score, reliability bins/Wilson intervals and calibration error, with model/catalog binding. These are experiment sample guards, not a claim that these sizes establish reliability. Representative errors, image-level separation and independent review are still essential. Production probability fields remain null.

Primary implementation/API references: https://rapidai.github.io/RapidOCRDocs/main/quickstart/ and https://github.com/RapidAI/RapidOCR. Model-specific licence/attribution references must be checked before release.

The candidate was also exercised through the actual API in the isolated environment with the app's pinned requirements (including Pillow 12.3.0). The sharper crop produced 25 parsed leaves and 15 flagged rows; missing decisions were rejected and explicit unknown decisions completed lookup. No ground-truth accuracy percentage is inferred. Re-run with `PYTHONPATH=backend` and the isolated interpreter on backend/tools/check_rapidocr_api.py.
