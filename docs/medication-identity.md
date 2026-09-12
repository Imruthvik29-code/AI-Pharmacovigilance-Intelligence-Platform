# Medication Identity Architecture

## Goal

Patients should be able to enter the medicine name printed on a strip, bottle, or prescription — including an Indian brand name — without the application asking them to understand RxNorm terminology.

The safety engine must still operate on verified standardized medication identities and ingredients. An LLM must never be the source of truth for a product's composition.

## Source strategy

The platform uses a layered terminology strategy:

1. **CDCI / Bharat Health Terminology Service (India)** for Indian generic and branded medicines.
2. **RxNorm** for standardized U.S./international medication concepts where available and for the existing ingredient-resolution graph.
3. Additional licensed or authoritative sources may be added later through the same identity boundary.

NRCeS currently describes Bharat Health Terminology Service (BHTS) as India's centralized FHIR R4 terminology infrastructure and explicitly lists Common Drug Codes of India (CDCI) for standardized generic and branded medicines. BHTS also exposes CSNOServ, including drug-information access through DISB.

The June 2026 CDCI flat-file release contained 93,019 branded medicines and 71,503 authorized product names, plus 10,174 generic medicines and 8,121 suppliers. The August 31, 2026 NRCeS release notice confirms CDCI and DISB are actively maintained and downloadable.

## Runtime identity flow

```text
patient input
    |
    v
brand / generic / ingredient search
    |
    +--> Indian CDCI / BHTS
    |
    +--> RxNorm
    |
    v
verified product candidate(s)
    |
    v
composition + strength + dose form + manufacturer
    |
    v
standardized ingredient identity
    |
    v
existing deterministic ADR / interaction / adherence engines
    |
    v
LLM explanation (never identity authority)
```

## Safety rules

- Never invent a product, ingredient, strength, manufacturer, or RxCUI.
- Never silently select between materially different products sharing a similar brand name.
- Unknown or ambiguous products must remain explicitly **not verified**.
- A verified brand record without a verified ingredient normalization must not be presented as fully analyzable by the safety engine.
- Preserve provenance for every imported or resolved identity.
- Keep the patient's selected `drug_id` as the stable internal reference used by existing safety rules.

## Current implementation boundary

`reference_drugs` remains the existing catalog abstraction. It already supports human-facing `name`/`generic_name`, provenance, RxCUI, RxNorm TTY, and active/retired state. RxNorm relationships remain in `rxnorm_concept_relations`.

Medication responses now also return the selected catalog identity (`drug_name`, `drug_generic_name`, `drug_term_type`, `drug_source`). This removes the previous dependency on browser-local storage for rendering a patient's medication record.

No licensed CDCI/SNOMED distribution files are committed to this repository. The application should consume an authorized CDCI/BHTS/DISB deployment or an authorized local package according to its license terms.

## Next integration step

Build the CDCI/BHTS adapter at the catalog boundary rather than adding brand-specific hard-coded mappings. The adapter should return a normalized candidate contract containing:

- source and source version
- source concept/product identifier
- product/brand name
- generic/clinical drug name
- ingredient(s) and strength(s)
- dose form
- supplier/manufacturer when available
- standardized concept mappings (SNOMED CT and/or RxNorm where available)
- verification status

Only candidates with sufficient evidence should enter `reference_drugs` and the deterministic safety path.

## Why this scales

This keeps the current safety architecture intact while making medication identity replaceable and source-aware. It supports future additions such as OCR from medicine packaging, multilingual names, FHIR/ABDM medication exchange, additional national terminology sources, and organization-specific formularies without putting brand-specific logic into the safety engine.
