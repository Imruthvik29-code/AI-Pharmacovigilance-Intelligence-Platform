"""
Pydantic schemas for the analysis endpoints (spec section 7):

    POST /patients/{id}/analyze
    GET  /patients/{id}/analysis

Response-only -- neither route accepts a client-supplied body. Analysis
is derived entirely server-side, from the patient's current data, via
the Phase 14 LangGraph workflow (`app/services/langgraph_workflow.py`),
matching the same read-only-request pattern already used by
`schemas/timeline.py`.

`risk_level` mirrors the database's `risk_level_enum`
(001_initial_schema.sql) and is nullable only because the underlying
column is nullable at the DB level (in practice, every run that reaches
the Persist Node has already computed a `SafetyScoreResult`, so this
will always be populated).

`llm_summary`/`llm_reasoning`/`llm_recommendations`/`confidence_score`/
`confidence_level` are nullable — populated when Gemini primary or
OpenRouter fallback succeeds with valid structured JSON (summary,
reasoning, recommendations, confidence_score 0-100, confidence_level
low/moderate/high), and NULL when every LLM provider fails or returns
unusable output — deterministic fields (safety_score, risk_level,
deterministic_result) always present, LLM fields additive per Phase 15.
See `app/services/llm_service.py` for prompt engineering, grounding,
and failure behavior.
"""
import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict

RiskLevel = Literal["low", "moderate", "high"]
ConfidenceLevel = Literal["low", "moderate", "high"]


class AnalysisRunResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    patient_id: uuid.UUID
    analysis_version: str
    deterministic_result: dict | None
    safety_score: int | None
    risk_level: RiskLevel | None
    llm_summary: str | None
    llm_reasoning: str | None
    llm_recommendations: str | None
    confidence_score: int | None
    confidence_level: ConfidenceLevel | None
    created_at: datetime
