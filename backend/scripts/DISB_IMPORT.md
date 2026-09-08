# CDCI / DISB medicine catalog import

The project can ingest the Indian medicine catalog from the official C-DAC / NRCeS Drug Information Service Bundle (DISB) into the existing `reference_drugs` PostgreSQL catalog.

## Source package

Use an authorized DISB release obtained from C-DAC / NRCeS. The current importer was built against **DISB v1.25**.

The source package is external and must **not** be committed to Git. In particular, do not add the ZIP, `Data/` Lucene indexes, generated TSV files, or the JAR to the repository.

Review the `License.txt` shipped with the exact source release before redistribution or public deployment. DISB's license distinguishes its non-SNOMED content from SNOMED CT content and separately notes third-party rights in brand/trade names.

## What is imported

The importer reads the `Data/data/medicine` Lucene index and creates/refreshes `reference_drugs` rows using:

- DISB medicine UUID -> `reference_drugs.id`
- `medicineName` -> `reference_drugs.name`
- `generic.genericName` -> `reference_drugs.generic_name`
- DISB `lastUpdatedon` -> `reference_drugs.source_updated_at`
- source -> `CDCI/DISB`
- `is_active` -> `true`, because the DISB medicine index does not expose a separate active flag

The medicine's SNOMED CT IDs, manufacturer, brand SCTID, license fields, and composition are exported only as part of the temporary extraction boundary and are **not** silently stored in unrelated RxNorm columns.

In particular, a CDCI/SNOMED identifier is never written to `reference_drugs.rxcui`. `rxcui` remains an RxNorm-only field.

## Why medicine records are the first phase

DISB v1.25 contains about 94k medicine records. Each medicine record already carries a human-facing product name and a generic name, which is enough to dramatically improve patient medication-name search without inventing normalization.

Composition-to-ingredient normalization is deliberately a separate phase. The safety engines currently resolve RxNorm identities through `rxnorm_concept_relations`; importing a textual composition and treating it as an RxNorm identity would be unsafe.

The target pipeline is:

```text
Indian product / brand name
        |
        v
CDCI / DISB verified medicine
        |
        +--> generic name / composition
        |
        v
verified standardized mapping where available
        |
        v
existing deterministic ADR / interaction engine
```

Unresolved mappings remain unresolved. The system must never guess an RxCUI from a brand name.

## Import command

From `backend/`:

```bash
python -m scripts.import_disb --disb-dir /path/to/DrugInfromationServiceBundle_v1.25
```

Controlled run:

```bash
python -m scripts.import_disb --disb-dir /path/to/DrugInfromationServiceBundle_v1.25 --limit 1000
```

Dry run:

```bash
python -m scripts.import_disb --disb-dir /path/to/DrugInfromationServiceBundle_v1.25 --dry-run
```

The importer requires JDK 17+ because the DISB package and its Lucene index are Java-based. It compiles the small `scripts/disb/LuceneMedicineExporter.java` helper against the Lucene core JAR shipped inside the supplied DISB package, streams the medicine index to a temporary TSV, and removes the temporary export when the run finishes.

Persistence is batched (500 rows by default), uses PostgreSQL upserts keyed by the source UUID, and refuses a source-ID collision with a non-CDCI catalog row. Re-running the same release is therefore idempotent.

## Coverage verified for DISB v1.25

The supplied package contains **93,905 medicine index documents**. The importer extracts one valid medicine identity per indexed document, subject to source rows containing the required `id` and `medicineName` fields.

The source package also contains separate generic and substance Lucene indexes. They are intentionally not imported into `reference_drugs` by this first phase because the current application schema has no verified composition relationship model for CDCI/SNOMED identities.

## Operational boundary

Keep the source package outside Git and outside the application image unless the deployment is explicitly licensed to contain it. The long-term production design is:

```text
Authorized CDCI / DISB source
          |
          v
one-time / controlled catalog ingestion
          |
          v
Supabase PostgreSQL reference_drugs
          |
          v
GET /api/v1/reference-drugs/search
```

The PWA never downloads the full catalog. It sends a short search query and the API returns a small ranked result set.
