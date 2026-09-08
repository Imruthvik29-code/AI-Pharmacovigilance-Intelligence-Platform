from datetime import timezone
from uuid import UUID

import pytest

from scripts.import_disb import _parse_row, _parse_timestamp


def test_parse_row_preserves_source_identity_and_generic_name() -> None:
    row = {
        "id": "19dc1243-ede4-43d5-9c4e-f41fe645d9bd",
        "medicineName": "Levomil (levofloxacin) 500 mg oral tablet",
        "genericName": "Levofloxacin 500 mg oral tablet",
        "lastUpdatedon": "2025-06-05",
    }

    result = _parse_row(row)

    assert result is not None
    assert result.id == UUID("19dc1243-ede4-43d5-9c4e-f41fe645d9bd")
    assert result.name.startswith("Levomil")
    assert result.generic_name == "Levofloxacin 500 mg oral tablet"
    assert result.source_updated_at is not None
    assert result.source_updated_at.tzinfo == timezone.utc


def test_parse_row_skips_missing_identity() -> None:
    assert _parse_row({"id": "", "medicineName": "Vasograin"}) is None
    assert _parse_row({"id": "19dc1243-ede4-43d5-9c4e-f41fe645d9bd", "medicineName": ""}) is None


def test_parse_row_rejects_invalid_source_uuid() -> None:
    with pytest.raises(ValueError, match="Invalid DISB medicine id"):
        _parse_row({"id": "not-a-uuid", "medicineName": "Example"})


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("2025-06-05", "2025-06-05T00:00:00+00:00"),
        ("2026-03-06 00:00:00", "2026-03-06T00:00:00+00:00"),
        ("2025-06-12 10:50:53.037000", "2025-06-12T10:50:53.037000+00:00"),
    ],
)
def test_parse_timestamp_supports_disb_formats(value: str, expected: str) -> None:
    assert _parse_timestamp(value).isoformat() == expected


def test_parse_timestamp_rejects_unknown_format() -> None:
    with pytest.raises(ValueError, match="Unsupported DISB lastUpdatedon"):
        _parse_timestamp("05/06/2025")
