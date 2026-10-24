# Ingredient phrases, cosine candidates and details

The Stage 1 flow is OCR → editable text → comma-separated phrases → normalized words/features → product-type-filtered cosine ranking → user review → descriptions. A phrase such as “sodium chloride” remains one ingredient, represented by multiple words. Commas/semicolons split top-level phrases; food compound lists expand to ordered leaves with parent_path metadata, while cosmetic/composite alias brackets remain intact. Empty brackets left by removed percentages are discarded. Original order and raw editable OCR text remain available.

## Candidate ranking

`identity-cosine-review-v1` uses local sparse TF-IDF word, adjacent-word and character 2/3/4-gram features. Each canonical name and alias is a separate vector variant; candidates are deduplicated by ingredient identity using the best variant. L2-normalized vector dot products are cosine similarities. Unknown query features contribute to the query norm, preventing extra unknown words from being ignored. Sparse inverted postings avoid comparing every feature with every ingredient. This is a spelling-oriented lexical vector model, not a downloaded semantic embedding model or LLM inference service.

The candidate catalog is filtered before fitting/ranking. Food searches include food-scoped and neutral identities; cosmetic searches include cosmetic-scoped and neutral identities. Other / unsure searches all identities. Neutral identity membership does not assign a food/cosmetic function. Schema v3 stores explicit ingredient contexts independently of description availability. It backfills the existing versioned adapter namespaces and description provenance; new adapter imports explicitly carry contexts. Adding an alias to an existing record does not silently widen its category. Review attribution, immutable sources and published descriptions are preserved.

The current local catalog yields 123 eligible food identities (121 food records plus two additional neutral starters) and 376 eligible cosmetic/neutral identities; there are 474 distinct identities overall. These counts describe source coverage, not real-label accuracy or legal authorisation.

Exact unambiguous canonical/alias identities and previously supported composite aliases remain confirmed matches. Ambiguous names and non-exact cosine candidates require review; a nearest neighbour is not automatically a known identity. At most three positive-similarity candidates are shown in details. Main-result suggestions use a versioned 0.30 cosine cutoff; this cutoff is not a confidence probability or an automatic acceptance rule. Unsupported phrases stay explicit. The scorer for v1 is unaffected.

## Show Details

A disclosure link beside **Ingredient text** is hidden by default in both clients. Opening it shows, per phrase, the word set, confirmed identity or unresolved state, closest candidate names/compared aliases, cosine similarity and available scan-wide OCR quality. The panel is available before and after confirmation. Opening it can request a draft matching preview; it does not confirm candidates or rewrite OCR text. Editing text or changing product type collapses it and invalidates old results. The native editor stays available after lookup so the link remains beside its label. Native guidance explicitly says that reviewing or opening details sends text to the configured API; this does not authorise image upload.

## Probability calibration remains outstanding

Cosine similarity is a geometric text-resemblance score, not a probability of correctness. A cosine of 0.9 cannot honestly be called a 90% chance of a correct identity. Even an exact name match can be wrong if OCR transcribed another valid ingredient name.

The API therefore returns `match_probability: null` and `probability_status: not_calibrated`, including for exact matches. The details panel explicitly says “Match probability: Not calibrated” and labels cosine scores separately. No synthetic test result is presented as real-world confidence calibration.

Reliable numeric probabilities require labelled, permitted real OCR samples with selected product type and a reviewed canonical identity (or no match). Include wrong nearest neighbours, out-of-catalog ingredients and close chemical-name confusions, not just successful pairs. Split by source image/product so calibration and held-out evaluation do not share label material. Fit and validate a calibration model using similarity, runner-up margin, OCR quality and match method; check reliability and Brier/error measures per product type. Bind it to the matcher, catalog snapshot and source versions. Until that evidence exists, a numeric probability would be invented. Default scans are not silently retained to collect this data.

## Verification

140 checks run with PostgreSQL enabled: 139 pass and one SQLite public-mode case is deliberately skipped; mobile TypeScript/lint pass. Android emulator smoke also verified the hidden-by-default disclosure, opening Show Details beside Ingredient text, the nearest cosine candidate and the explicit uncalibrated probability label. Tests cover comma phrases/word sets, category isolation, exact and misspelled names, alias collisions, unknown features, stable ties, absence of fabricated probabilities and context-preserving migration.

`python -B tools/check_matching_details.py` from backend checks actual local OCR → phrase → vector output, category filtering, hidden-by-default details, availability after lookup, edit/type invalidation and mobile-width layout in Chrome. Synthetic “Sodlum chlorlde” ranks SODIUM CHLORIDE first in Food while staying unconfirmed; NIACINAMIDE is excluded from the Food catalog and available in Cosmetics. The script is an integration check, not calibration data.

[Desktop details](screenshots/stage1-cosine-details.png). [Phone-width browser details](screenshots/stage1-cosine-details-mobile.png).

[Native Android details](screenshots/stage1-native-cosine-details.png).

## Mandatory individual confirmation

Both clients show review cards in the main review step, independently of Show Details. Non-exact or ambiguous identities, resolved identities with cosine below 0.80 (or unavailable similarity), and available scan-wide OCR quality below 0.75 require an explicit decision. These versioned thresholds are review heuristics, not calibrated probabilities. Native OCR does not supply numeric quality; every non-exact identity is still flagged.

For each flagged phrase, confirm a displayed candidate, correct the editable text and review again, or choose **Keep unknown**. Lookup stays disabled until all flagged phrases have decisions. The server independently returns HTTP 409 with pending positions when decisions are missing. A chosen identity is labelled `user_confirmed`; keeping unknown clears any provisional match. Raw phrases/order and uncalibrated probability labels remain intact.

Decisions bind to the scan, phrase, position, product type, matcher version and displayed candidate IDs. Changed input, duplicate decisions and unoffered candidates are rejected (422). Text/type edits clear client decisions. Scan capabilities retain only expiry and scalar OCR quality for 30 minutes, with no server retention of image or ingredient text. This scalar ensures low-quality exact OCR matches cannot bypass review at lookup.

Regression checks cover partial review, low-quality exact matches, ambiguous aliases, explicit rejection, stale and cross-scan decisions. `python -B tools/check_ingredient_confirmation.py` checks the Chrome flow and phone-width layout. [Confirmation preview](screenshots/stage1-ingredient-confirmation.png).

Food parent paths are shown beside leaf names in review/results; group headings are not counted a second time. Nested original percentage text remains in leaf raw fields, while percentages are excluded from name matching. This does not add concentration or product scoring. The offline calibration experiment is documented in [OCR comparison](OCR-ENGINE-COMPARISON.md); it never enables production probabilities automatically.

## Explicit recovery for broken OCR brackets

The supplied maggi masala 3 photo reproduces a case where OCR returns substantial text but broken parentheses prevent structured parsing. Review previously displayed an incorrect all-reviewed message with zero rows. Both clients now show why lookup is blocked and offer **Review comma-separated entries**.

Recovery is an explicit choice with a warning: blend hierarchy cannot be preserved. It leaves the original editable OCR text untouched, treats bracket characters as uncertain separators within each comma/semicolon entry, and requires a separate candidate/unknown decision for every entry, including exact names. Raw entry text is preserved. It never silently repairs nesting or accepts guesses. Correct text and use structured review when group meaning matters.

POST /scans/{id}/review requires the scan capability, retains scalar OCR quality and creates a new review session. parsing_mode is structured or comma_review and is bound to that session; changing it during confirmation is rejected. Shared operations retain this mode metadata alongside quality/expiry, without retaining ingredient text. Missing or partial decisions still return 409.

The actual third-photo browser regression completes lookup after 26 entry decisions and checks the original text is unchanged. Repeat from backend with `python -B tools/check_maggi_recovery.py`. `check_native_recovery.py` checks the Android broken-bracket recovery flow.
