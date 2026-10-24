# Stage 1 implementation and release status

The engineering increment is implemented locally. Stage 1 is not signed off for release. Product scoring remains exclusively in v1.

## Implemented in this increment

- 486 distinct ingredient identities in SQLite and PostgreSQL, 479 with a published description in at least one context. Food has 134 scoped identities: 133 have food descriptions; palm oil has a draft description pending rights review. Neutral fallback adds two eligible identities, giving 136 food-search identities. No cosmetic function is used as a food description.
- Added onion/garlic/celery powders, nonfat and whole milk powders, whey variants/protein concentrate and casein coverage. Existing rice-starch/garlic identities were reused. New federal-source descriptions use explicit automated development-review attribution. Independent editorial review remains outstanding.
- Food compound lists expand into ordered leaves. For `Seasoning (Salt, Spices [Cumin, Turmeric])`, Cumin carries `parent_path: ["Seasoning", "Spices"]`. Group labels are retained as context rather than counted again as ingredients. Percentages remain in raw leaf text; cosmetic/composite alias behavior is preserved. Unsupported or malformed structures require correction. Nesting is bounded to 12 levels and 200 leaves.
- Browser/native review and results show parent groups. Every uncertain identity still needs an explicit candidate/unknown decision. Parent changes invalidate API confirmation keys.
- OCR evaluation compares Tesseract WASM, system Tesseract, optional RapidOCR and supplied native recordings. It validates permissions/review attribution, duplicate images and product separation between baseline/held-out sets. Metrics include ordered-token precision/recall, errors and per-condition/context summaries. Two supplied photos are diagnostics, not a 30-image benchmark.
- Offline isotonic calibration experiment provides Brier score, reliability bins, Wilson intervals and calibration error. It requires real reviewed examples, both correct/incorrect cases, separate products and both launch contexts. It binds output to matcher/catalog hashes. Runtime probabilities remain null until independently validated.
- Public mode supports PostgreSQL-backed capabilities and request counters across workers, HMAC-hashed secrets/client buckets, expiry cleanup, no-store responses, HTTPS/host checks and rate-limit retry responses. The HTTPS proxy configuration validates. No public deployment was performed.

## Validation

See [current validation](STAGE1-VALIDATION.md), [OCR comparison](OCR-ENGINE-COMPARISON.md), [pilot/device checklist](PILOT-CHECKLIST.md) and [deployment preparation](RELEASE-OPERATIONS.md).

## Work needing external evidence or access

| Gate | What is still required |
|---|---|
| Real-label OCR evaluation | At least 30 permitted real images, reviewed phrase-level ground truth, baseline and held-out products, and quality targets agreed before held-out evaluation. Current inputs are two photos of one product. |
| Numeric match probabilities | A representative labelled calibration corpus and independent reliability review. The experiment is not a deployed probability model. |
| Content and source rights | Independent review of aliases/descriptions; palm-oil source commercial reuse review. Local automated attribution does not satisfy this gate. |
| Physical Android testing | Pixel and Motorola e300 are available per owner. Only emulator-5554 is currently connected to ADB. Connect/authorize phones for actual camera, crop, permission, cache and TalkBack checks. |
| iOS | Native build/signing and camera/Vision/cache/VoiceOver validation. No iPhone or configured iOS build access has been supplied. |
| Pilot | Representative product users/tasks, correction effort and description comprehension. Synthetic fixtures do not count as a product pilot. |
| Dependencies | node-forge has an unresolved advisory with no patched stable release observed. Four dependency paths remain; braces advisory was withdrawn. |
| Hosting | A real domain/host, protected operational secrets, reviewed content, TLS/load/privacy validation and deployment execution. Config preparation is complete; live operations are not signed off. |

No user scan is silently retained for building either corpus. Templates under validation/ are deliberately marked `is_real: false` and must be replaced with actual permitted/reviewed examples.

## 24 October: Maggi catalog coverage

Added 12 ingredient identities and 84 label aliases across both local databases,
including food-context potassium chloride on its existing identity. The corrected
Maggi diagnostic text resolves 24/25 leaves with 23 cited food descriptions.
`Mineral and Vitamin` remains unspecified and palm-oil description rights remain
pending. All 147 backend checks completed: 146 pass and one intentional skip.
[Accumulating catalog maintenance](INGREDIENT-DATABASE.md) documents repeatable
imports, explicit automated development review and preserved rejection history.
This increment does not establish real-image OCR accuracy or independent review.
