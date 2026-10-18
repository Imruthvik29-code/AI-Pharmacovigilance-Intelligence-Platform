"""Closed evidence selection for explanations, not an entailment classifier.

The model may select source-bound statements, never supply displayable prose.
Exact IDs and a request-local digest prevent unsupported or stale claims from
crossing into persistence. Source text is quoted as recorded, not certified as
true. No causal assessments are derived from dates or unstructured notes.
"""
import hashlib
import json
from dataclasses import asdict, dataclass

from app.analysis.safety_score_engine import SafetyScoreResult
from app.analysis.timeline_engine import TimelineContext
from app.services.evidence_retrieval import EvidenceBundle
from app.services.patient_context_builder import PatientContext


class EvidenceSelectionError(ValueError):
    """Unsupported, incomplete or incorrectly scoped evidence selection."""


@dataclass(frozen=True)
class Statement:
    id: str
    text: str
    section: str
    source: str
    required: bool = False


@dataclass(frozen=True)
class EvidenceCatalog:
    scope: str
    statements: tuple[Statement, ...]

    def prompt_data(self) -> dict:
        return {"scope": self.scope,
                "statements": [asdict(s) for s in self.statements]}


def build_catalog(
    patient: PatientContext, result: SafetyScoreResult,
    evidence: EvidenceBundle, timeline: TimelineContext,
) -> EvidenceCatalog:
    if timeline.entries and timeline.patient_id != patient.patient_id:
        raise EvidenceSelectionError("Patient/timeline scope mismatch.")
    statements: list[Statement] = []

    def add(
        key: str, text: str, section: str, source: str,
        required: bool = False,
    ) -> None:
        statements.append(Statement(key, text, section, source, required))

    def quote(value: object) -> str:
        return json.dumps(value, ensure_ascii=True, default=str)

    add("score", f"Recorded safety score: {result.safety_score}/100. "
        f"Risk level: {result.risk_level}.", "summary", "safety_score_result", True)
    for i, penalty in enumerate(result.penalties):
        add(f"penalty:{i}", f"Recorded {penalty.category} deduction: "
            f"{penalty.points} points ({penalty.severity}). "
            f"Ledger description: {quote(penalty.description)}.",
            "reasoning", f"safety_score_result.penalties[{i}]", True)
    for category, findings in (
        ("interaction", result.interaction_findings),
        ("adr", result.adr_findings), ("adherence", result.adherence_findings),
    ):
        for i, finding in enumerate(findings):
            if category == "interaction":
                detail = (
                    f"{quote(finding.drug_a_name)} + {quote(finding.drug_b_name)}; "
                    f"recorded severity: {finding.severity}; rule mechanism: "
                    f"{quote(finding.mechanism)}; source: {quote(finding.source)}"
                )
            elif category == "adr":
                detail = (
                    f"{quote(finding.drug_name)}; rule reaction risk: "
                    f"{quote(finding.reaction_description)}; recorded severity: "
                    f"{finding.severity}; frequency: {quote(finding.frequency_class)}; "
                    f"source: {quote(finding.source)}"
                )
            else:
                detail = (
                    f"{quote(finding.drug_name)}; taken: {finding.taken}; "
                    f"missed: {finding.missed}; skipped: {finding.skipped}; "
                    f"due: {finding.due}; adherence rate: {finding.adherence_rate}"
                )
            add(f"finding:{category}:{i}",
                f"Recorded engine {category} finding (rule/result, not a confirmed "
                f"patient reaction): {detail}.", "reasoning",
                f"safety_score_result.{category}_findings[{i}]", True)
    if not result.penalties and not any((result.interaction_findings,
                                        result.adr_findings, result.adherence_findings)):
        add("no-findings", "No findings were detected by the supplied rules for "
            "this record; this is not proof of clinical safety.", "reasoning",
            "safety_score_result", True)
    for i, medication in enumerate(patient.active_medications):
        add(f"medication:{i}", "Recorded medication (not proof of ingestion): "
            f"{quote(medication.drug_name)}; dose: {quote(medication.dose)}; "
            f"recorded purpose: {quote(medication.purpose_text)}; recorded start "
            f"date: {medication.start_date.isoformat()}.", "reasoning",
            f"patient_context.active_medications[{medication.id}]")
    for i, symptom in enumerate(patient.active_symptoms):
        add(f"symptom:{i}", f"Recorded symptom: {quote(symptom.description)}; "
            f"recorded severity: {quote(symptom.severity)}; recorded onset date: "
            f"{symptom.onset_date.isoformat()}.", "reasoning",
            f"patient_context.active_symptoms[{symptom.id}]")
    for category, bundles, findings in (
        ("interaction", evidence.interaction_evidence, result.interaction_findings),
        ("adr", evidence.adr_evidence, result.adr_findings),
        ("adherence", evidence.adherence_evidence, result.adherence_findings),
    ):
        for i, bundle in enumerate(bundles):
            if bundle.finding not in findings:
                raise EvidenceSelectionError("Evidence/finding binding mismatch.")
            for j, item in enumerate(bundle.medical_evidence):
                add(f"rule:{category}:{i}:{j}", "Supplied general rule quotation "
                    f"(not a confirmed patient reaction), source {quote(item.source)}: "
                    f"{quote(item.statement)}.", "reasoning",
                    f"evidence_bundle.{category}[{i}].medical[{j}]")
            for j, item in enumerate(bundle.personal_evidence):
                add(f"note:{category}:{i}:{j}", "Recorded note quotation "
                    f"(assessment/observation as documented, not independently "
                    f"verified), source {quote(item.source)}, recorded_at "
                    f"{quote(item.occurred_at.isoformat() if item.occurred_at else None)}: "
                    f"{quote(item.statement)}.", "reasoning",
                    f"evidence_bundle.{category}[{i}].personal[{j}]", True)
    add("limits", "Available evidence cannot independently establish a cause. "
        "Chronology alone does not establish causation or a clinical association. "
        "Recorded assessments remain attributed assessments, not model-proven "
        "conclusions. Missing evidence remains unknown; conflicting evidence "
        "remains unresolved.", "reasoning", "explanation_policy", True)
    add("guidance", "Discuss the recorded findings and uncertainties with your "
        "prescriber or pharmacist; this explanation does not prescribe changes.",
        "recommendations", "explanation_policy", True)
    # Bind the complete inputs, including IDs and omitted chronology, to this
    # invocation. No module/global patient state is retained.
    scope = hashlib.sha256(json.dumps(
        [asdict(patient), asdict(result), asdict(evidence), asdict(timeline)],
        sort_keys=True, default=str,
    ).encode("utf-8")).hexdigest()
    return EvidenceCatalog(scope, tuple(statements))


def render_selection(data: dict, catalog: EvidenceCatalog) -> dict:
    expected = {"scope", "summary", "reasoning", "recommendations",
                "confidence_score", "confidence_level"}
    if set(data) != expected or data.get("scope") != catalog.scope:
        raise EvidenceSelectionError("Invalid selection fields or request scope.")
    known = {s.id: s for s in catalog.statements}
    rendered = {}
    for section in ("summary", "reasoning", "recommendations"):
        ids = data[section]
        if (not isinstance(ids, list) or not ids
                or any(not isinstance(key, str) for key in ids)
                or len(ids) != len(set(ids))):
            raise EvidenceSelectionError("Empty, duplicate or invalid selection.")
        if any(key not in known or known[key].section != section for key in ids):
            raise EvidenceSelectionError("Unsupported claim or section binding.")
        required = {s.id for s in catalog.statements
                    if s.section == section and s.required}
        if not required.issubset(ids):
            raise EvidenceSelectionError("Required findings or uncertainty omitted.")
        # Source order, not model order, prevents reordered conflicting notes
        # or a disclaimer being repurposed as an affirmative clinical claim.
        rendered[section] = "\n\n".join(
            s.text for s in catalog.statements if s.section == section and s.id in ids)
    return {**rendered, "confidence_score": data["confidence_score"],
            "confidence_level": data["confidence_level"]}
