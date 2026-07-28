# Changelog

All notable changes to this project will be documented here.

---

## [Unreleased]

### Added

- Initial project structure
- Project specification
- SQL schema
- Development workflow
- Claude project instructions
- **Phase 1 — Database:**
  - Seed data migration (`002_seed_data.sql`): 12 curated reference drugs,
    7 interaction rules, 13 ADR rules, sourced from established FDA label
    facts.
  - SQLAlchemy async engine/session setup (`app/db/session.py`).
  - Environment-based configuration via `pydantic-settings` (`app/core/config.py`).
  - SQLAlchemy ORM models mirroring the frozen schema 1:1 (`app/db/models.py`).
  - Database integration tests (`tests/test_database.py`): connectivity,
    seed data integrity, FK cascade behavior, enum defaults.

### Changed

None

### Fixed

None
