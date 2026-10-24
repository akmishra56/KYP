# Accumulating local ingredient catalog

Updated 24 October 2026.

The local ingredient database accumulates source-backed identities, label aliases,
context-specific descriptions and immutable source snapshots. Updates insert new
records; they do not replace existing identities, erase evidence, discard review
history or overturn rejected sources/descriptions. SQLite and the configured local
PostgreSQL catalog can receive the same increment.

From `backend`, prepare and import drafts:

```powershell
python -B tools/update_food_catalog.py --sync-postgres
```

For explicit automated development-source comparison after inspecting the pinned
manifest and evidence:

```powershell
python -B tools/update_food_catalog.py --review-development --sync-postgres
```

Add `--refresh` to retrieve current evidence. Without it, validated local snapshots
are reused. The updater backs up SQLite under ignored `data/backups/` before any
database change and writes a secret-free `data/food-update-report.json`. The Docker
PostgreSQL service must be running for sync (`docker compose up -d --wait postgres`
from the project root). Omit `--sync-postgres` for SQLite only. This is an explicit
maintenance command, not a scheduled internet crawl and not an upload of user scans.

## Adding future evidence

1. Research the missing label name using primary sources. Verify whether it is a
   spelling/form, an extract, a mixture, an additive code or an unspecified category.
2. Add exact FDA inventory names and CAS-pinned existing-identity crosswalks to
   `backend/kyp/food-policy.json`. Missing/ambiguous source records stay in the report.
3. For supplementary evidence, update `backend/kyp/food-enrichment-policy.json`:
   explicit source URL, reuse terms, attribution, required identity text, bounded
   description and supporting excerpts. New domains need an explicit adapter
   allowlist change and review. A trusted domain alone does not verify a claim.
4. Retrieve evidence, inspect it, and record offline regression fixtures. Exercise
   exact label coverage and negative examples before reviewing the new records.
5. Review sources and descriptions using the existing CLI, or explicitly use the
   automated development comparison above. Independent editorial and scientific
   review, where applicable, remains a separate release gate.

The supplementary adapter uses HTTPS allowlisted origins, bounded downloads,
content hashes, cached retrieval dates and required source/excerpt checks. Content
changes get new immutable source IDs. Repeated unchanged imports do not add duplicate
identities, descriptions or review events. Supplementary aliases retain evidence in
the description provenance (`label_alias_evidence`), including source references.
This is a curated evidence manifest, not an automatic guarantee that arbitrary new
summaries are correct. Do not add OCR misspellings as ingredient aliases.

## Maggi coverage increment

FDA food inventory: anise/aniseed, fenugreek, capsicum extract and food-context
potassium chloride (CAS crosswalk to the existing cosmetic identity).
FDA spice definitions: separate dried onion/garlic and ground red chilli/green
cardamom forms. Federal CFR 182.20: separate coriander and cumin extracts.
Federal CFR 100.155: iodized/iodised salt, distinct from plain sodium chloride.
Federal CFR 101.22: natural flavouring as a broad, composition-unspecified category.
UK Food Standards Agency (OGL v3): E635 identity. ChEBI (CC BY 4.0): E508 identity;
existing ChEBI E330 evidence is reused. Functional labels such as `Flavour enhancer
(635)`, `Thickener (508)` and `Acidity regulator (330)` get explicitly pinned aliases;
bare numbers, different codes, botanical oils and OCR errors remain unresolved.
No Indian authorisation or safety finding is inferred from foreign source listings.

The corrected diagnostic Maggi label has 25 leaves: 24 identities match and 23
have food descriptions after explicit development review. `Mineral and Vitamin`
remains unspecified; no particular nutrient is guessed. Palm oil matches while its
description remains withheld for source-rights review. The diagnostic uses corrected
text and is not evidence of OCR accuracy or independently reviewed ground truth.
The manufacturer page is corroboration for label names, not imported product copy;
formulation percentages from another pack do not overwrite the photographed label.

Sources:

- https://www.fda.gov/regulatory-information/search-fda-guidance-documents/cpg-sec-525750-spices-definitions
- https://www.fda.gov/food/food-additives-petitions/substances-added-food-formerly-eafus
- https://www.govinfo.gov/content/pkg/CFR-2025-title21-vol3/xml/CFR-2025-title21-vol3-sec182-20.xml
- https://www.govinfo.gov/content/pkg/CFR-2025-title21-vol2/xml/CFR-2025-title21-vol2-sec100-155.xml
- https://www.govinfo.gov/content/pkg/CFR-2025-title21-vol2/xml/CFR-2025-title21-vol2-sec101-22.xml
- https://data.food.gov.uk/regulated-products/food_authorisations/e-635
- https://www.ebi.ac.uk/chebi/CHEBI:32588
- https://www.nestleprofessional.in/foods/maggi-masala-ae-magic
