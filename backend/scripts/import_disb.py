"""Import the DISB v1.25 medicine catalog into ``reference_drugs``.

DISB ships its medicine catalog as a Lucene index. This importer uses the
small Java exporter in ``scripts/disb/LuceneMedicineExporter.java`` to stream
that index to a temporary TSV and then persists validated rows to PostgreSQL
in bounded transactions.

The DISB package is intentionally an external input: it must never be copied
into this repository. Keep the source package under the terms in its
License.txt and record the source/version used for an import.

Usage from ``backend/``::

    python -m scripts.import_disb --disb-dir /path/to/DrugInfromationServiceBundle_v1.25

For a controlled run::

    python -m scripts.import_disb --disb-dir /path/to/DISB --limit 1000

The importer only adds/refreshes ``ReferenceDrug`` catalog rows. It does not
modify interaction or ADR rules and does not assign RxCUIs to CDCI/SNOMED
identities. RxNorm normalization remains a separate, verified mapping step.
"""
from __future__ import annotations

import argparse
import asyncio
import csv
import logging
import shutil
import subprocess
import tempfile
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert

# Allow ``python scripts/import_disb.py`` from backend/ as well as
# ``python -m scripts.import_disb``.
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.db.models import ReferenceDrug  # noqa: E402
from app.db.session import AsyncSessionLocal, engine  # noqa: E402

logger = logging.getLogger("scripts.import_disb")

SOURCE_NAME = "CDCI/DISB"
DEFAULT_BATCH_SIZE = 500
EXPORTER_SOURCE = Path(__file__).resolve().parent / "disb" / "LuceneMedicineExporter.java"
EXPECTED_HEADER = (
    "id",
    "medicineName",
    "medicineSctid",
    "brandSctid",
    "brandName",
    "manufacturerName",
    "manufacturerSctid",
    "manufacturerCountry",
    "genericSctid",
    "genericName",
    "licenseNumber",
    "licenseStatus",
    "lastUpdatedon",
)


@dataclass(frozen=True)
class DisbMedicine:
    id: str
    name: str
    generic_name: str | None
    source_updated_at: datetime | None


def _normalise(value: str | None) -> str | None:
    if value is None:
        return None
    value = value.strip()
    return value or None


def _parse_timestamp(value: str | None) -> datetime | None:
    value = _normalise(value)
    if not value:
        return None
    for fmt in ("%Y-%m-%d", "%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M:%S.%f"):
        try:
            return datetime.strptime(value, fmt).replace(tzinfo=timezone.utc)
        except ValueError:
            continue
    raise ValueError(f"Unsupported DISB lastUpdatedon value: {value!r}")


def _parse_row(row: dict[str, str]) -> DisbMedicine | None:
    source_id = _normalise(row.get("id"))
    name = _normalise(row.get("medicineName"))
    if not source_id or not name:
        return None
    return DisbMedicine(
        id=source_id,
        name=name,
        generic_name=_normalise(row.get("genericName")),
        source_updated_at=_parse_timestamp(row.get("lastUpdatedon")),
    )


def _locate_lucene_jar(disb_dir: Path) -> Path:
    candidates = list(disb_dir.rglob("lucene-core-*.jar"))
    if not candidates:
        raise FileNotFoundError(
            "Could not find lucene-core-*.jar inside the DISB package. "
            "Pass the extracted DISB v1.25 directory containing disb-1.25.jar and Data/."
        )
    return candidates[0]


def _locate_medicine_index(disb_dir: Path) -> Path:
    candidates = [
        disb_dir / "Data" / "data" / "medicine",
        disb_dir / "data" / "medicine",
    ]
    for candidate in candidates:
        if candidate.is_dir() and (candidate / "segments_1").exists():
            return candidate
    raise FileNotFoundError(
        "Could not find the DISB medicine Lucene index (Data/data/medicine)."
    )


def _compile_exporter(lucene_jar: Path, work_dir: Path) -> Path:
    javac = shutil.which("javac")
    if javac is None:
        raise RuntimeError("JDK 17+ is required: javac was not found on PATH.")
    class_file = work_dir / "LuceneMedicineExporter.class"
    command = [
        javac,
        "-cp",
        str(lucene_jar),
        "-d",
        str(work_dir),
        str(EXPORTER_SOURCE),
    ]
    subprocess.run(command, check=True)
    if not class_file.exists():
        raise RuntimeError("DISB exporter compilation completed without producing a class file.")
    return class_file


def _export_tsv(disb_dir: Path, output: Path) -> int:
    java = shutil.which("java")
    if java is None:
        raise RuntimeError("JDK 17+ is required: java was not found on PATH.")

    lucene_jar = _locate_lucene_jar(disb_dir)
    medicine_index = _locate_medicine_index(disb_dir)
    with tempfile.TemporaryDirectory(prefix="disb-exporter-") as temp:
        work_dir = Path(temp)
        _compile_exporter(lucene_jar, work_dir)
        command = [
            java,
            "-cp",
            f"{lucene_jar}{__import__('os').pathsep}{work_dir}",
            "LuceneMedicineExporter",
            str(medicine_index),
            str(output),
        ]
        subprocess.run(command, check=True)

    with output.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.reader(handle, delimiter="\t")
        header = tuple(next(reader, ()))
    if header != EXPECTED_HEADER:
        raise RuntimeError(f"Unexpected DISB export header: {header!r}")

    with output.open("r", encoding="utf-8", newline="") as handle:
        return max(sum(1 for _ in csv.reader(handle, delimiter="\t")) - 1, 0)


async def _import_batch(rows: list[DisbMedicine], dry_run: bool) -> tuple[int, int, int]:
    if dry_run:
        return len(rows), 0, 0

    now = datetime.now(timezone.utc)
    values = [
        {
            "id": medicine.id,
            "name": medicine.name,
            "generic_name": medicine.generic_name,
            "source": SOURCE_NAME,
            "source_updated_at": medicine.source_updated_at,
            "is_active": True,
            "created_at": now,
            "updated_at": now,
        }
        for medicine in rows
    ]

    async with AsyncSessionLocal() as db:
        existing = {
            row.id: row.source
            for row in (
                await db.execute(
                    select(ReferenceDrug.id, ReferenceDrug.source).where(
                        ReferenceDrug.id.in_([medicine.id for medicine in rows])
                    )
                )
            ).all()
        }

        safe_values = []
        skipped_conflicts = 0
        for value in values:
            previous_source = existing.get(value["id"])
            if previous_source is not None and previous_source != SOURCE_NAME:
                skipped_conflicts += 1
                logger.warning(
                    "Skipping DISB source-id collision for %s: existing source=%s",
                    value["id"],
                    previous_source,
                )
                continue
            safe_values.append(value)

        if safe_values:
            statement = pg_insert(ReferenceDrug).values(safe_values)
            statement = statement.on_conflict_do_update(
                index_elements=[ReferenceDrug.id],
                set_={
                    "name": statement.excluded.name,
                    "generic_name": statement.excluded.generic_name,
                    "source": statement.excluded.source,
                    "source_updated_at": statement.excluded.source_updated_at,
                    "is_active": statement.excluded.is_active,
                    "updated_at": statement.excluded.updated_at,
                },
            )
            await db.execute(statement)
        await db.commit()

    inserted = sum(1 for medicine in rows if medicine.id not in existing)
    updated = len(rows) - inserted - skipped_conflicts
    return len(rows), inserted, updated


async def run(args: argparse.Namespace) -> None:
    disb_dir = args.disb_dir.expanduser().resolve()
    if not disb_dir.is_dir():
        raise FileNotFoundError(f"DISB directory does not exist: {disb_dir}")

    with tempfile.TemporaryDirectory(prefix="disb-catalog-") as temp:
        export_path = Path(temp) / "medicine.tsv"
        discovered = _export_tsv(disb_dir, export_path)
        planned = min(discovered, args.limit) if args.limit is not None else discovered
        logger.info("DISB source: %s", SOURCE_NAME)
        logger.info("DISB catalog rows discovered: %d", discovered)
        logger.info("Rows selected for import: %d", planned)

        processed = inserted = updated = 0
        batch: list[DisbMedicine] = []
        with export_path.open("r", encoding="utf-8", newline="") as handle:
            reader = csv.DictReader(handle, delimiter="\t")
            for row in reader:
                if processed >= planned:
                    break
                medicine = _parse_row(row)
                if medicine is None:
                    logger.warning("Skipping DISB row without id/name")
                    continue
                batch.append(medicine)
                if len(batch) >= args.batch_size:
                    _, batch_inserted, batch_updated = await _import_batch(batch, args.dry_run)
                    processed += len(batch)
                    inserted += batch_inserted
                    updated += batch_updated
                    batch.clear()
                    logger.info("Processed %d/%d", processed, planned)

            if batch:
                _, batch_inserted, batch_updated = await _import_batch(batch, args.dry_run)
                processed += len(batch)
                inserted += batch_inserted
                updated += batch_updated

        logger.info(
            "DISB import complete: discovered=%d processed=%d inserted=%d updated=%d dry_run=%s",
            discovered,
            processed,
            inserted,
            updated,
            args.dry_run,
        )


async def main() -> None:
    parser = argparse.ArgumentParser(description="Import DISB v1.25 medicines into reference_drugs")
    parser.add_argument("--disb-dir", type=Path, required=True, help="Extracted DISB v1.25 directory")
    parser.add_argument("--batch-size", type=int, default=DEFAULT_BATCH_SIZE)
    parser.add_argument("--limit", type=int, default=None, help="Maximum rows to import")
    parser.add_argument("--dry-run", action="store_true", help="Export/validate without writing PostgreSQL")
    parser.add_argument("--log-level", default="INFO", choices=("DEBUG", "INFO", "WARNING", "ERROR"))
    args = parser.parse_args()
    if args.batch_size < 1:
        parser.error("--batch-size must be >= 1")
    if args.limit is not None and args.limit < 1:
        parser.error("--limit must be >= 1")

    logging.basicConfig(level=getattr(logging, args.log_level), format="%(asctime)s %(levelname)s %(message)s")
    try:
        await run(args)
    finally:
        await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
