# Food catalog development review — 23 October 2026

Stage 1 now includes food and cosmetics. The first food increment contains **110 food-context descriptions**: 108 exact FDA inventory records and two curated identity/category definitions (wheat flour and broad spices). Twenty-three FDA identities crosswalk to the existing repository by manifest-pinned name and CAS; other records retain separate identities. The combined local catalog has 463 identities and 457 identities with at least one published description across contexts. These are development counts, not measured real-label coverage.

## Sources and reuse

- [FDA Substances Added to Food](https://www.fda.gov/food/food-additives-petitions/substances-added-food-formerly-eafus): public download includes substance names, alternate names and technical effects. The retrieved export identifies its update as 8 September 2026. A bounded 135-name manifest matched 108 exact names after review of the source spellings. Missing candidates remain in the generated report; the importer never accepts a fuzzy search result.
- [FDA website reuse policy](https://www.fda.gov/about-fda/about-website/website-policies): FDA website content is generally public domain unless otherwise noted. Source attribution and retrieval date are retained. Source/technical-effect summaries are adapted, without an FDA endorsement claim. The inventory includes material from non-FDA entities and also formerly used/prohibited substances. Membership must never be treated as approval, legal-use advice, or a safety finding in any country.
- [ChEBI](https://www.ebi.ac.uk/chebi/about), CC BY 4.0: exact three-star identities, CAS checks and source-listed synonyms verify E330/E-330/INS-330 (citric acid) and E422/E-422/INS-422 (glycerol). Separator normalization supports E 330 and INS 330 without equating arbitrary bare numbers to additive codes. Other E/INS codes remain unsupported until separately verified.
- [Wheat flour definition](https://www.govinfo.gov/content/pkg/CFR-2025-title21-vol2/xml/CFR-2025-title21-vol2-sec137-105.xml) and [spice definition](https://www.govinfo.gov/content/pkg/CFR-2025-title21-vol2/xml/CFR-2025-title21-vol2-sec101-22.xml): public U.S. federal text from the 2025 CFR edition, used for basic definitions, not current regulatory assessments. Flour aliases preserve wheat specificity; generic “flour” is not forced to wheat. “Spices” matches only a broad category and does not reveal blend constituents.

## Review and limitations

Descriptions and source excerpts were compared automatically. The recorded reviewer explicitly states **Codex automated food source/role comparison; not human or scientific review**. A few bounded identity definitions/alias shortenings are curated in the versioned policy. Independent editorial review remains required before public release. Importing never auto-approves anything. Earlier draft descriptions superseded by code evidence remain rejected with a reason; malformed HTML bullet aliases from the first draft import were removed before local publication.

FDA roles are phrased as listed technical effects, with at most two selected per ingredient. They do not establish an ingredient’s actual role, dose or effect in a photographed product. The FDA source does not establish Indian or EU authorisation. Generic mixtures are not expanded into guessed constituents.

Food, cosmetic and neutral descriptions share identity records but remain independently selected. Food lookups prefer food text, then domain-neutral identity text. They never use cosmetic functions as a fallback. Cosmetics follow the reverse rule. “Other / unsure” shows neutral descriptions only. Changing the product type invalidates old results. The API defaults to neutral context for older callers; updated clients send product_context explicitly. Direct GET /ingredients/ID accepts the same product_context query parameter. Image review uses X-Product-Context.

Known gaps include onion/onion powder, palm oil, milk/powders and several sweeteners or additives. An unavailable or ambiguously sourced name remains unresolved or lacks a description. The Wikidata endpoint refused the requests during this investigation; no records were imported from it. Neither onion oil nor a milk enzyme was substituted for a staple food. Nested compound lists remain intact and may need individual correction/lookup; children are not yet separately resolved. Food “Contains:” and “May contain” advisory statements are excluded from ingredient tokens, with the raw editable text preserved. No allergen assessment is added.

## Reproduce

From backend: `python -B -m kyp.food --db data/kyp.sqlite3`. New content always enters as drafts. The FDA response is cached, bounded to 16 MB and parsed as CSV despite the download’s Excel MIME type. Spreadsheet expressions are treated as inert strings. Source schema changes, ambiguous records and failed crosswalks stop or quarantine the relevant import. Versioned names, aliases, role priorities, food codes and staple summaries live in kyp/food-policy.json. Offline fixture records and standards carry the same attribution and public-domain/ChEBI terms.

Automated checks cover exact-source support, crosswalk drift, duplicate names, unsupported roles, food/cosmetic isolation, source rejection, neutral fallback, E/INS separators and food advisories. Real-product coverage and OCR accuracy still require the planned representative benchmark and pilot.

## Remaining-work increment

The development catalog now has 474 distinct identities and 120 published food-context descriptions: 113 exact FDA inventory records and seven bounded federal standard/label definitions. Added entries cover onion/garlic/celery powders, nonfat/whole milk powders and whey/casein records. Sources, source checks and citation/role comparisons carry automated-development attribution, not independent editorial/scientific sign-off. Both databases are synchronized without overwriting review history.

A separate palm-oil identity and short draft use a limited FAO Codex definition excerpt. Its source explicitly says commercial reuse review pending; its description is not published. No broad milk-powder phrase is silently equated with whole or nonfat milk. Food eligibility includes 121 food-scoped and two neutral identities.

A review packet containing aliases, descriptions, citations and recorded decisions is exported locally to ignored backend/data/editorial-review.json. Independent review and representative product coverage remain release gates. See ../docs/STAGE1-REMAINING-WORK.md.

## 24 October: verified Maggi label coverage

Both local catalogs now contain 486 identities and 133 food descriptions across
134 food-scoped identities. The increment adds 12 identities, food membership for
existing potassium chloride and 84 aliases. FDA inventory source records cover
aniseed, fenugreek, capsicum extract and potassium chloride. Supplementary FDA/CFR
sources cover dried vegetables, ground spice forms, extracts, iodized salt and the
broad natural-flavouring category. UK FSA OGL v3 evidence identifies E635; ChEBI
CC BY 4.0 identifies E508; existing E330 evidence is reused. Alias evidence is
retained in description provenance, with immutable cited snapshots. No manufacturer
product copy was imported. Automated development comparisons are explicitly
attributed; independent review remains required. Palm-oil rights remain pending.

See [maintenance and source URLs](../docs/INGREDIENT-DATABASE.md). The corrected
25-leaf Maggi diagnostic now has 24 matched identities and 23 food descriptions;
`Mineral and Vitamin` does not name specific nutrients and remains unresolved.
