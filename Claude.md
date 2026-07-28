# CLAUDE.md

## Project Rules

This repository follows the document:

pharmacovigilance-spec-v1.md

This specification is the single source of truth.

Do NOT redesign the architecture.

---

## Development Principles

- Implement only the phase requested.
- Do not modify completed phases unless fixing bugs.
- Keep deterministic analysis separate from LLM reasoning.
- Do not introduce new frameworks without approval.
- Write modular code.
- Use type hints.
- Follow PEP8.
- Keep functions small.
- Add comments where logic is non-obvious.

---

## AI Responsibilities

The LLM must NEVER:

- Diagnose diseases.
- Invent drug interactions.
- Invent ADRs.
- Calculate safety scores.

The LLM ONLY:

- Explains deterministic findings.
- Summarizes evidence.
- Generates recommendations.
- Produces readable reports.

---

## Deterministic Layer

Python performs:

- Drug interaction detection.
- ADR matching.
- Adherence analysis.
- Timeline reasoning.
- Safety score calculation.

---

## Testing Rules

Every completed phase must be tested before continuing.

Never leave failing code.

---

## Coding Style

- FastAPI backend
- SQLAlchemy ORM
- Pydantic models
- Async endpoints where appropriate
- Modular services
- Reusable utilities

---

## Git Workflow

Never modify multiple unrelated modules in one task.

Each implementation request should correspond to one logical Git commit.

---

## If unsure

Follow the specification.

Do not guess.
