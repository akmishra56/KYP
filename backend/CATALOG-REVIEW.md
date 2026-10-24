# Stage 1 catalog review — 2026-10-23

The local development catalog contains 376 ingredient identities: four ChEBI/Wikidata starters plus 375 exact active CosIng records, with three explicit CAS-checked crosswalks. Of these, 369 have locally published short descriptions; seven retain “description unavailable”. This is a cosmetic ingredient expansion; it is not a food ingredient corpus or a reliable Maggi-label lookup.

## Evidence and scope

The bounded candidate manifest and role paraphrases are versioned in `kyp/cosing-policy.json` (cosing-descriptions-v1.1). Ingestion uses the European Commission’s public CosIng search, requires exact INCI names and active ingredient records, and keeps immutable, content-addressed ingredient and function glossary snapshots. Descriptions cite both the ingredient’s listed roles and the glossary definition. Up to two roles are described, without guessing the function or concentration in a particular product. “In cosmetics” preserves domain context even if an ingredient also occurs in food.

Source: https://ec.europa.eu/growth/tools-databases/cosing/

Reuse policy reviewed: https://commission.europa.eu/legal-notice_en — Commission-owned material is generally CC BY 4.0 unless otherwise indicated. Local source records retain Commission attribution and the licence link. This is an automated terms comparison, not legal review.

CosIng limitations: https://single-market-economy.ec.europa.eu/sectors/cosmetics/cosmetic-ingredient-database_en — inventory membership does not establish safety, authorisation or legal use. Neither matching nor the descriptions makes those claims.

## Review decisions

Codex compared every used role paraphrase with the retrieved glossary and validated exact citation excerpts for every generated description. The reviewer recorded in both databases explicitly says **automated CosIng role/source comparison; not human or scientific review**. New ingestion remains draft-only; the adapter never approves content. Superseded v1 drafts were rejected with a reason, not deleted. Independent editorial/content review remains a public-release gate.

Only AQUA/water (7732-18-5), GLYCERIN/glycerol (56-81-5) and CITRIC ACID/citric acid (77-92-9) crosswalk to existing identities. No general synonym or food-name equivalence is invented. A single checksum-valid CAS may be an alias; multiple CAS values are not collapsed. Ambiguous identities remain unresolved.

Three candidate names were not found exactly: SPHINGOSINE, SODIUM ALGINATE, IRON OXIDES. Seven active records have no supported mapped description: RETINOL, RETINYL PALMITATE, RETINYL ACETATE, CERAMIDE NG, DIETHYLHEXYL SYRINGYLIDENEMALONATE, HIPPOPHAE RHAMNOIDES FRUIT OIL and CARRAGEENAN. They are not filled from general model knowledge.

## Reproduce and review

From `backend`, run `python -B -m kyp.cosing --db data/kyp.sqlite3`. The bounded raw cache and generated import/report live under ignored `data/`; a refresh retrieves the public source again. Three small recorded source records and relevant function definitions are in `tests/fixtures/cosing.json` for offline regression tests, under the same Commission attribution/licence. A fresh import is not automatically published.

Use `python -B -m kyp.cli stats`, `pending --state pending --limit 20 --full`, and `history description ID` to inspect decisions. Rejection commands require a named reviewer and reason. Rejected sources immediately hide their dependent descriptions; re-import never resets a decision. Schema v2 preserves existing approvals and adds an audit event for them. SQLite-to-PostgreSQL migration copies review history and preserves existing destination decisions.
