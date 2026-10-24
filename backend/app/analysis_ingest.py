"""
Read the AI's analysis from the repair MR and store it as ADVISORY (B3, §A5).

Trigger: GitLab MR `open` webhook on `duo/fix/<incident_id>` (after repair.proposed).
Fetch:   sentinel/incidents/<incident_id>/analysis.json at the MR head commit (GitLab API).
Check:   JSON Schema docs/contracts/analysis.schema.json, incident id match, secret scan.
Store:   Analysis on the current attempt + a ledger event `analysis.recorded`.
         Invalid or missing analysis -> ledger event `analysis.rejected` (state unchanged).

The analysis never moves the state machine: AI output is never proof.
"""

import json
import logging
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import quote

import httpx
import jsonschema

from app.config import settings
from app.models.entities import Analysis, EventRecord
from app.persistence.factory import get_repository
from app.security import find_secret_values

logger = logging.getLogger("sentinel.analysis")

_BACKEND_ROOT = Path(__file__).resolve().parent.parent
SCHEMA_CANDIDATES = [
    _BACKEND_ROOT / "contracts" / "analysis.schema.json",
    _BACKEND_ROOT.parent / "docs" / "contracts" / "analysis.schema.json",
]
_VALIDATOR: jsonschema.Draft202012Validator | None = None


def analysis_path(incident_id: str) -> str:
    return f"sentinel/incidents/{incident_id}/analysis.json"


def _validator() -> jsonschema.Draft202012Validator:
    global _VALIDATOR
    if _VALIDATOR is None:
        for path in SCHEMA_CANDIDATES:
            if path.exists():
                _VALIDATOR = jsonschema.Draft202012Validator(json.loads(path.read_text(encoding="utf-8")))
                break
        else:
            raise RuntimeError("analysis.schema.json not found")
    return _VALIDATOR


def fetch_analysis(incident_id: str, ref: str) -> tuple[dict | None, str | None, str | None]:
    """Returns (document, file_url, error)."""
    token = settings.gitlab_read_token or settings.gitlab_flow_token
    if not (settings.gitlab_project_id and token):
        return None, None, "GITLAB_PROJECT_ID / GITLAB_READ_TOKEN not configured"
    base = settings.gitlab_api_url.rstrip("/")
    path = quote(analysis_path(incident_id), safe="")
    url = f"{base}/projects/{quote(str(settings.gitlab_project_id), safe='')}/repository/files/{path}/raw"
    try:
        resp = httpx.get(url, params={"ref": ref}, headers={"PRIVATE-TOKEN": token}, timeout=15.0)
    except httpx.HTTPError as exc:
        return None, None, f"GitLab request failed: {type(exc).__name__}"
    if resp.status_code == 404:
        return None, None, f"{analysis_path(incident_id)} not found at {ref}"
    if resp.status_code >= 300:
        return None, None, f"GitLab returned HTTP {resp.status_code}"
    try:
        doc = resp.json()
    except ValueError:
        return None, None, "analysis.json is not valid JSON"
    return doc, f"{analysis_path(incident_id)}@{ref}", None


def to_analysis(attempt_id: str, doc: dict, file_ref: str | None) -> Analysis:
    suspected = doc.get("suspected_change")
    return Analysis(
        attempt_id=attempt_id,
        facts=[f"{f['fact']} [{f['evidence_ref']}]" for f in doc.get("facts", [])],
        hypotheses=[f"{h['hypothesis']} (confidence: {h['confidence']})" for h in doc.get("hypotheses", [])],
        missing_evidence=[str(m) for m in doc.get("missing_evidence", [])],
        suspected_change=json.dumps(suspected) if suspected else None,
        file_ref=file_ref,
    )


def validate_analysis(incident_id: str, doc: object) -> str | None:
    """Returns an error message, or None if the document is acceptable."""
    if not isinstance(doc, dict):
        return "analysis.json must be a JSON object"
    errors = list(_validator().iter_errors(doc))
    if errors:
        e = errors[0]
        where = ".".join(str(p) for p in e.path) or "root"
        return f"schema violation at '{where}': {e.message[:200]}"
    if doc.get("incident_id") != incident_id:
        return f"analysis is for {doc.get('incident_id')!r}, not {incident_id!r}"
    if find_secret_values(doc):
        return "analysis contains a credential-like value"
    return None


def _ledger(incident_id: str, etype: str, ref: str, data: dict, summary: str) -> None:
    get_repository().save_event(
        EventRecord(
            id=f"evt-analysis-{incident_id}-{etype.split('.')[-1]}-{ref[:12]}",
            entity_type="Incident",
            entity_id=incident_id,
            type=etype,
            source="sentinel/backend/analysis_ingest",
            source_job_id=ref,
            at=datetime.now(UTC).isoformat(),
            data=data,
            summary=summary,
        )
    )


def ingest_analysis(incident_id: str, ref: str) -> bool:
    """Fetch, validate and store the analysis for the incident's current attempt."""
    repo = get_repository()
    inc = repo.get_incident(incident_id)
    if inc is None or not inc.recovery_attempts:
        return False
    att = inc.recovery_attempts[-1]
    if not (settings.gitlab_project_id and (settings.gitlab_read_token or settings.gitlab_flow_token)):
        logger.info("Analysis ingestion skipped for %s: GitLab read access not configured", incident_id)
        return False

    doc, file_ref, error = fetch_analysis(incident_id, ref)
    if error is None:
        error = validate_analysis(incident_id, doc)
    if error is not None:
        logger.warning("Analysis for %s not stored: %s", incident_id, error)
        _ledger(incident_id, "analysis.rejected", ref, {"reason": error}, f"Analysis not stored: {error}")
        return False

    repo.set_attempt_analysis(incident_id, att.id, to_analysis(att.id, doc, file_ref))
    _ledger(
        incident_id,
        "analysis.recorded",
        ref,
        {"advisory": True, "outcome": doc.get("outcome"), "file_ref": file_ref,
         "facts": len(doc.get("facts", [])), "hypotheses": len(doc.get("hypotheses", []))},
        "AI analysis stored (advisory, not proof).",
    )
    return True
