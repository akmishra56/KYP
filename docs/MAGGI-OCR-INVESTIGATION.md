# Maggi photo OCR investigation — 23 October 2026

Image: docs/images/maggi masala.jpeg. The original image was left unchanged. All processing took place locally.

## Reproduced failure

The local OCR engine returned text, but the text contained misread parentheses. POST /scans/image immediately fed that text into the strict ingredient parser, which raised `Unbalanced brackets: correct the ingredient text`. The API returned 422 before the browser could show the extracted text. This incorrectly presented a parsing/review problem as an OCR failure.

The photograph is also difficult for the current engine: small condensed italic print, blur, reflective packaging and several adjacent text columns. Single-block segmentation mixed ingredients with addresses, nutrition and other package text. EXIF orientation was already respected on the server; browser cropping was explicitly tested to preserve the upright 1280 x 960 orientation.

## Changes

- Successful OCR now returns its raw text for review even when the ingredient parser cannot split it. The response includes a parse warning and no parsed tokens in that case. It does not guess missing punctuation or ingredient names.
- Confirmation remains strict: unchanged malformed text cannot be submitted as a valid ingredient list. Editing and reviewing corrected text works normally.
- The browser previews the photo and offers a draggable crop plus keyboard-operable percentage controls. Cropping occurs before upload, with explicit server-processing consent still required. The preview export was verified at 397 x 317 pixels for a selected ingredient region.
- The native picker enables its crop editor and gives ingredient-panel guidance. Server fallback warnings remain visible in the mobile review flow.
- Food-label parsing stops at nutrition information/facts, how-to-use text, manufacturer/marketer sections and ingredient-content annotations rather than treating them as more ingredients.

## Validation

55 backend/integration tests pass across SQLite and PostgreSQL. Mobile TypeScript and Expo lint pass. A headless-browser regression using the supplied real photo verified orientation, no image upload before consent, visible OCR text, crop export, parser warnings, correction and unresolved repository matches. Browser errors: none.

Screenshot: screenshots/maggi-ocr-review.png. Repeat with `python -B backend/tools/check_maggi_ocr.py` while KYP is running on port 8001; this diagnostic requires Playwright and local Chrome. Aggregate results are in ignored backend/data/maggi-ocr-report.json.

## Remaining limitation and suggested capture

The supplied photo still does not yield a trustworthy complete ingredient transcription with the current engine, including after cropping and layout experiments. The fix makes the failure visible and recoverable; it is not a claim of improved transcription accuracy. Flatten the packet and photograph just the ingredient panel at close range, in focus, with diffuse light and no reflected glare. Crop before reading and compare every detected ingredient to the label.

At the time of the initial investigation, the repository had only four starter identities. The later food catalog now resolves source-backed names such as Salt and Sugar; onion powder and other coverage gaps remain explicit. A clearly read food ingredient can therefore still be unmatched or have no description. OCR quality, identity coverage and description availability are separate states; none implies safety.

## Later candidate and catalog checkpoint

Onion powder is now covered with a food description. An isolated RapidOCR candidate was compared locally on both supplied images and ingredient crops; the sharper crop is substantially more readable, though spelling/layout errors remain. Its actual API diagnostic produced 25 ingredient leaves with 15 requiring confirmation. This is not an independently labelled accuracy benchmark, and the default OCR engine is unchanged. See [candidate comparison](OCR-ENGINE-COMPARISON.md) and [current validation](STAGE1-VALIDATION.md).
