# Current Stage 1 validation

This is a working local development build, not an MVP release sign-off. Scoring is excluded. This checkpoint supersedes the earlier four-starter/49-test validation snapshot.

| Check | Observed result |
|---|---|
| Backend/source/database suite | 140 checks: 139 pass, one intentional SQLite skip for public mode; actual PostgreSQL public-mode test passes |
| Mobile TypeScript / lint | Pass after final native group labels and accessibility names |
| Catalog | SQLite/PostgreSQL synchronized: 474 identities, 467 with a published description in at least one context; 120 food-context descriptions |
| Nested food parsing | Ordered leaf matching, preserved parent paths/raw percentage text, malformed-input/depth/size guards pass |
| Confirmation enforcement | Missing/partial/stale/invalid decisions rejected; explicit candidate/unknown choices pass in browser and Android |
| Browser representative flow | Seven nested-food leaves, six identities, five published food descriptions; palm identity remains description-unavailable pending rights; mystery remains unknown |
| Browser recovery/layout | Network failure then retry, keyboard details link, 320px/390px layout and category/edit invalidation pass; no browser errors |
| Android AVD | Native compound review/result paths and three food descriptions pass at font_scale 1.3; original setting restored |
| Existing Android photo/OCR | Earlier generated-label photo/native-OCR/cache flow passed; this is not physical-camera validation |
| Optional RapidOCR candidate | Local evaluation on both Maggi photos, full/cropped, completed; clearer sharper-crop output still contains mistakes |
| Candidate OCR API | Sharper crop returns 25 parsed leaves and 15 flagged rows; missing confirmations return 409, explicit unknown decisions return a lookup; probabilities remain uncalibrated |
| Shared operational state | Cross-instance PostgreSQL capabilities, hashed storage, atomic rate counters, expiry, HTTPS/host enforcement and response headers pass |
| HTTPS configuration | Caddy configuration validates in an isolated container without public ports; no real domain/certificate was deployed |
| Dependency audit | Four high-severity paths remain from node-forge; braces advisory withdrawn; no patched stable node-forge observed |
| Real-image benchmark / calibration | Not completed: two images of one product are insufficient; tooling and private corpus templates provided |
| Physical devices | Pixel and Motorola e300 available per owner, not connected to ADB; only emulator-5554 observed |
| iOS / screen readers / real pilot | Not verified in this environment |

## Evidence and repeatability

- `scripts/test.ps1 -Postgres` runs the backend suite and mobile typecheck; run mobile lint separately.
- From backend: `python -B tools/check_stage1_readiness.py`, `check_ingredient_confirmation.py`, `check_matching_details.py` and `check_food_catalog.py` exercise the local browser/API. These use explicitly synthetic representative phrases rather than a real-user pilot.
- `tools/check_native_compounds.py` runs the AVD compound/scaling check and restores font_scale in a finally block. `check_native_confirmation.py` checks partial review and explicit decisions from an initially open app home screen.
- The isolated candidate check is `data/ocr-evaluation-env/Scripts/python.exe -B tools/check_rapidocr_api.py` with PYTHONPATH pointing at backend. It runs actual local OCR/parser/confirmation code on the supplied sharper crop; it does not establish token accuracy.
- `tools/compare_maggi_ocr.py` records local engine/crop diagnostics. Optional API dependencies and engine pins can coexist in the isolated environment; production dependencies/default engine were not replaced.
- Screenshots: [nested food browser](screenshots/stage1-nested-food.png), [native enlarged-text food](screenshots/stage1-native-nested-food.png), [individual confirmation](screenshots/stage1-ingredient-confirmation.png).

## Remaining gates

Independent editorial/source review, the permitted real-label benchmark, real calibration evidence, physical Android/iOS and TalkBack/VoiceOver checks, representative pilot, dependency disposition and live hosting/privacy/load validation remain open. See [current work status](STAGE1-REMAINING-WORK.md), [pilot checklist](PILOT-CHECKLIST.md), [OCR findings](OCR-ENGINE-COMPARISON.md) and [operations](RELEASE-OPERATIONS.md). Synthetic tests and automated source comparison cannot sign those off.

Maggi 3 recovery regression: actual local OCR reproduces broken brackets/zero structured rows. Explicit comma review yields 26 entries and completes lookup only after individual decisions. Original text and OCR quality remain intact; normal nested flow still passes. Mobile lint/typecheck pass.
