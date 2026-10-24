# Stage 1 image orientation

Select a label photo, crop to the ingredients and inspect the preview. Both clients provide **Rotate left**, **Rotate right**, **Auto orient** and **Reset rotation** before **Read photo**. Manual turns are 90 degrees. Camera EXIF orientation is respected first; content rotation is applied to those displayed pixels. The original photo-library image is never overwritten.

In the browser, manual rotation runs entirely in local canvas. The selected crop follows the same physical region through a turn; exported JPEG pixels match the preview. Reset rotation returns to the original camera-corrected orientation while preserving the selected region. Auto orient checks the cropped region on the configured local API after the existing image-processing consent checkbox is checked. It rotates the full preview and remaps the crop when a clear direction is found. Images and raw OCR text are not retained by the API.

In the native app, photo selection now opens a preview rather than immediately starting OCR. Rotate or auto orient, then tap Read photo. Native Auto orient first tries four rotations with on-device OCR. Some native engines read text independently of the visual rotation and return equally good text for several candidates. If the local result is ambiguous or unavailable, an explicit consent dialog offers server orientation; declining sends no image. The server result is applied locally to the preview. Manual controls remain available if the server is unavailable or also uncertain.

Native preview/cache copies are cleared after reading (including failed reading or fallback cancellation), discard, replacement, text review or normal component unmount. Candidate rotation files are cleared after each attempt. Library originals remain untouched. As with other cache-based workflows, forced app/process termination is not a verified cleanup path; broader device/privacy validation remains a release gate.

## Automatic decision and limits

The versioned `orientation-en-v1` policy checks the four quarter-turn positions. It compares English label-word evidence and requires both enough evidence and a clear margin over the runner-up. This heuristic is independent of ingredient matching and scoring. Its status is not a calibrated confidence percentage or an OCR accuracy claim. Weak, blank, non-English or ambiguous results leave the current preview unchanged and request manual rotation. Always review the result.

The server endpoint is `POST /images/orient` with JPEG/PNG/WebP bytes and `X-Image-Processing-Consent: yes`. It shares the OCR upload bounds (8 MB, 20 megapixels) and two-job concurrency limit. It creates no scan/session token. A single local Tesseract WASM worker checks four temporary images within a 45-second subprocess timeout, then deletes those files. It returns clockwise rotation, confident/uncertain status and policy version, without extracted label text. This endpoint does not require a new OCR engine or external OCR vendor.

This increment fixes quarter-turn orientation. Small-angle deskew, document-edge/perspective correction, curvature and glare correction are separate preprocessing work; no scanner-equivalence claim is made.

## Verification

- 97 backend/source/integration tests pass with PostgreSQL enabled, including consent, limits, ambiguity and timeout/success cleanup.
- Mobile TypeScript and lint pass. The actual native TypeScript orientation selector passes eight shared decision fixtures; native and backend policy files are checked for equality.
- Real local OCR of a synthetic label at 0/90/180/270 degrees selected the expected correction in all four cases. Blank input remained uncertain. This is a synthetic integration check, not the planned real-label benchmark.
- Android emulator smoke: selected a synthetic sideways label through the system picker/crop editor, verified manual rotation visually, observed the explicit native fallback consent dialog, and confirmed that the resulting cached image had upright 1600×380 pixels. Read photo then removed both active draft image copies. Physical-device and iOS checks remain pending.
- Chrome verified that manual rotation changes exported pixels, crop coordinates follow the image, auto orientation changes the preview, and no orientation image is uploaded without consent. The Maggi consent/crop/correction regression still passes; its imperfect OCR output remains editable.

Run `python -B tools/check_image_orientation.py` from backend against the running local API. Run `node tools/check-orientation.cjs` from mobile for the native decision fixtures.

[Browser orientation preview](screenshots/stage1-image-orientation.png). [Native manual rotation preview](screenshots/stage1-native-orientation-rotated.png).
