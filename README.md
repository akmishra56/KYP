# KYP — Stage 1 working development build

MVP scope: food and cosmetic ingredient repository, OCR, text review, conservative identity matching and short sourced descriptions. v1 scoring is excluded. v2 onward remains outside scope.

## Try it locally

The development API uses port **8001** because another application already occupies 8000 on this machine. Do not stop that service.

From the project root in PowerShell:

```powershell
# PostgreSQL: Docker Desktop must be running.
.\scripts\dev.ps1
```

Open http://127.0.0.1:8001 for the local browser client, or http://127.0.0.1:8001/docs for API documentation. The script loads the ignored .env file and starts the project database. Credentials are not logged. To use SQLite instead, run `.\scripts\dev.ps1 -SQLite`.

The development environment currently has the required Python packages, mobile packages and English OCR model installed. For a fresh environment:

```powershell
cd backend
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
npm.cmd ci --prefix ocr-runtime
node ocr-runtime/setup-model.mjs
```

Activate the virtual environment or use its Python interpreter when running the scripts. Fresh PostgreSQL setup also requires copying .env.example to .env and replacing the local credentials. Docker Compose binds the database only to 127.0.0.1:55432. `docker compose stop` stops the database without deleting its data.

## What works

- SQLite and PostgreSQL repository adapters with parameterized SQL, transactions and versioned schema migrations and review audit history.
- Canonical/alias matching, exact composite INCI matching such as Water (Aqua/Eau), and conservative fuzzy suggestions. Ambiguous names stay unresolved.
- A description can be unavailable even when an identity matches. No safety meaning is inferred from matching.
- Source snapshots, immutable citations, draft imports, named review attribution and description/source detail.
- Camera/photo input in the native Expo client, on-device OCR first, explicit consent for server fallback, label review, results and source links.
- A project-local Tesseract WASM fallback, without requiring a system-wide OCR installation. It loads its installed model locally and does not send images to an OCR vendor.
- A browser development client for trying the API on this computer.

## Starter data and ingestion

The local catalog now contains **486 identities**, including the cosmetic corpus and **133 food-context descriptions** (117 exact FDA inventory records, seven staple definitions and nine supplementary definitions/categories). **479 identities have at least one sourced description across contexts**; seven have none, including the palm-oil draft awaiting source-rights review. Select Food, Cosmetics or Other / unsure before reviewing a label. Food and cosmetic functions never cross categories; neutral identity text may be a fallback. See [food catalog review](backend/FOOD-CATALOG-REVIEW.md) and [cosmetic catalog review](backend/CATALOG-REVIEW.md) for sources and limits.

See [starter data review](backend/STARTER-DATA-REVIEW.md) for each description and its supporting excerpt. The four initial basic descriptions were checked by Codex against the retrieved definitions and are explicitly attributed to **automated source comparison**, not independent human/scientific review. The app returns that review attribution. Licence and attribution links accompany published descriptions. Public release still needs editorial/content review.

```powershell
cd backend
python -B -m kyp.ingest --db data/kyp.sqlite3
python -B -m kyp.cosing --db data/kyp.sqlite3
python -B -m kyp.food --db data/kyp.sqlite3
python -B -m kyp.cli stats
python -B -m kyp.cli pending --limit 20 --full
```

Ingestion caches bounded API responses and imports drafts. It never auto-approves new descriptions. A reviewed seed manifest prevents identity/alias drift; source changes or unsupported aliases are rejected. The starter source policy and CosIng manifest/role mapping are versioned in kyp/source-policy.json and kyp/cosing-policy.json. This implementation uses structured sources and curated summaries; it does not yet integrate LLM extraction.

For other imports, use the JSON shape in examples/import-template.json. That template is synthetic format documentation and must not be presented as factual ingredient content. Source support excerpts must exist in the snapshot, and descriptions remain drafts until a named reviewer attests to support. Source approval records the reviewer's reuse-permission check; the CLI does not inspect licences automatically.

```powershell
python -B -m kyp.cli import PATH_TO_IMPORT.json
python -B -m kyp.cli approve-source SOURCE_ID --reviewer REVIEWER_NAME
python -B -m kyp.cli approve-description DESCRIPTION_ID --reviewer REVIEWER_NAME
python -B -m kyp.cli reject-description DESCRIPTION_ID --reviewer REVIEWER_NAME --reason "Wording needs correction"
python -B -m kyp.cli reject-source SOURCE_ID --reviewer REVIEWER_NAME --reason "Permission needs review"
python -B -m kyp.cli history description DESCRIPTION_ID
python -B -m kyp.cli pending --state rejected --limit 20
```

Rejected sources hide their dependent descriptions immediately. Re-import preserves decisions; schema v2 retains approval/rejection history with reviewer, reason and timestamp. Batch matching reads the catalog once per confirmation, without caching decisions across requests.

Reviewer identity must state whether a review was automated or human. No source-retrieval timestamp, matching success or automated comparison should be presented as qualified scientific review.

## Native mobile app

See [mobile setup](mobile/README.md). Install dependencies with `npm ci` from mobile. On-device OCR needs a native development build; Expo Go cannot load the custom OCR module. Android builds require the Android SDK/JDK; iOS builds require macOS/Xcode or a separately configured build service. A physical phone needs an explicitly configured reachable API URL; localhost is the phone itself.

The mobile app uses a minimal paper/violet/mint design with a small cartoon bean detective. Photo-cache copies are cleared after processing, with library originals left untouched. Native OCR supplies no confidence values, so users review every ingredient.

## Verification

```powershell
# From the project root; also type-checks the mobile app.
.\scripts\test.ps1 -Postgres
```

Current verification: **147 checks: 146 pass and one intentional SQLite-only public-mode skip** with PostgreSQL enabled, plus mobile TypeScript and lint checks. The running Chrome/API catalog check passes with no browser errors; run `python -B tools/check_catalog.py` from backend against the populated local API. [Cosmetic browser screenshot](docs/screenshots/stage1-expanded-catalog.png). Food/API and mobile-width browser checks also pass: `python -B tools/check_food_catalog.py`. [Food browser screenshot](docs/screenshots/stage1-food-catalog.png).

Backend tests cover repository review gates, unsupported/citationless claims, immutable and idempotent imports, source-specific recorded fixtures, ambiguous/fuzzy/composite matching, scan access/expiry, explicit image consent, upload limits and temporary-file deletion. PostgreSQL tests create isolated named schemas and clean them up, including setup failures. A migration test verifies preservation of reviewed descriptions and repeatable copying.

Real OCR smoke: from backend, set PYTHONPATH to the backend directory and run `python -B tools/smoke_ocr.py`. This generates one high-contrast synthetic label in memory. It is an engine/integration check, not a real-label benchmark. The aggregate report goes to ignored data/ocr-smoke-report.json. Set KYP_DATABASE_URL to repeat it against PostgreSQL.

To evaluate a permitted real corpus: `python -B -m kyp.evaluate_ocr MANIFEST.json`. Each manifest record requires image, expected_tokens, tags and permission. The evaluator reports exact ordered-token precision/recall overall and by condition. It does not copy images or label text into its aggregate report. At least 30 labelled real packaging images and agreed held-out accuracy thresholds are still required before release.

## Database migration

Set KYP_DATABASE_URL to the destination PostgreSQL URL, then run from backend:

```powershell
python -B -m kyp.migrate --sqlite data/kyp.sqlite3
```

The migration is transactional and non-destructive: it preserves immutable identities, evidence snapshots and review attribution, rejects content conflicts and preserves existing destination reviews. It never drops tables or replaces an existing destination record. Both local databases have the expanded development catalog. Migration also copies audit events and preserves existing destination decisions.

## Privacy and operational limits

The API never saves scan images or raw label text. Local-mode capabilities expire after 30 minutes and are process-local; restarting the local server invalidates them. Public mode uses shared PostgreSQL capabilities and supports multiple workers with the same operational secret. Image uploads require explicit consent, accept JPEG/PNG/WebP, and are bounded to 8 MB / 20 megapixels. Temporary preprocessing files are deleted after success or failure.

Public-mode shared PostgreSQL sessions, rate limiting and HTTPS/host guards are implemented and tested. Live deployment remains gated on operational/privacy checks and source/editorial review. See [deployment preparation](docs/RELEASE-OPERATIONS.md). The generated Expo toolchain has actual unresolved dependency audit findings documented in [dependency review](mobile/DEPENDENCY-REVIEW.md); no clean-audit claim is made. Keep development services local.

## Remaining Stage 1 release work

Independently review the expanded corpus and test representative product-label coverage; verify representative real-product coverage and review the newly added staples. Validate 30+ real packaging images, native camera/OCR/cache behavior on devices, iOS native linking, VoiceOver/TalkBack, scaling and pilot usability. Resolve or formally review the toolchain audit findings before public distribution. No scoring or later-stage features are required to finish this MVP.

## Packaging-photo OCR and correction

Crop closely to the ingredient panel before reading; exclude nutrition tables and addresses. The browser supports drawing a crop or editing percentage controls. The native picker offers its crop editor. OCR text remains editable even when brackets or punctuation prevent parsing; fix the text and review it again before confirming. The original Maggi photo remains too blurry/reflective for reliable full transcription with this engine. See [the investigation and verified fix](docs/MAGGI-OCR-INVESTIGATION.md).


## Image orientation before OCR

Both clients now provide a photo preview with Rotate left/right, Auto orient and Reset rotation. Native photo selection pauses at this preview; tap Read photo when the label is upright. Camera orientation metadata is respected automatically. Auto orient checks four quarter-turn positions; uncertain results keep the image unchanged. Native auto orientation tries on-device OCR first and asks for separate consent if it needs the server. Browser auto orientation uses the existing image-processing consent. Manual rotation stays local and the crop follows the image. See [behavior and validation](docs/IMAGE-ORIENTATION.md).


## Ingredient matching details

Comma-separated ingredient phrases are represented by word/character TF-IDF vectors and ranked by cosine similarity against the selected product type's catalog. Open **Show Details** beside **Ingredient text** for word sets, closest candidates, similarity and available OCR quality. Details are collapsed by default and reset after edits or a product-type change. Non-exact candidates remain suggestions for review. Match probabilities are explicitly **not calibrated**; cosine similarity is not presented as a probability. See [matching behavior and calibration requirements](docs/INGREDIENT-MATCHING.md). Schema v3 adds product-type membership and preserves existing reviews; the SQLite/PostgreSQL migration copies those memberships.

Uncertain ingredient identities now require individual confirmation in the main review step (choose a candidate, correct text, or keep unknown). Both clients and the API enforce completion. See [ingredient matching](docs/INGREDIENT-MATCHING.md).

## Current Stage 1 checkpoint

Nested food groups now resolve into ordered leaf ingredients with visible parent paths in both clients. The new food descriptions are available locally; palm oil remains explicitly description-unavailable pending rights review. [Remaining release gates and delivered work](docs/STAGE1-REMAINING-WORK.md), [OCR candidate findings](docs/OCR-ENGINE-COMPARISON.md), and [device/pilot checklist](docs/PILOT-CHECKLIST.md) are the current checkpoint. RapidOCR is an isolated, optional candidate and has not replaced the default engine.

## Accumulating ingredient database

The Maggi coverage increment is installed in both local databases: 486 identities,
1,023 aliases and 133 published food-context descriptions. Corrected diagnostic
label text resolves 24 of 25 ingredient leaves, with 23 food descriptions; unspecified
"Mineral and Vitamin" remains unresolved and palm-oil description rights remain pending.
This measures catalog coverage of corrected text, not OCR accuracy.

From backend, `python -B tools/update_food_catalog.py --review-development --sync-postgres`
adds allowlisted, cited evidence with explicit automated development-review attribution.
It backs up SQLite and preserves identities, evidence and prior decisions. Omit
`--review-development` to leave new content as drafts; use `--refresh` to retrieve
updated sources. Run `python -B tools/verify_maggi_catalog.py --postgres` to verify
scan/review/results against both populated databases. See the [database maintenance
guide](docs/INGREDIENT-DATABASE.md) for source policy, review requirements and expansion.
