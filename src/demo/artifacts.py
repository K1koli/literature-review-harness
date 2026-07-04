from __future__ import annotations

import json
import re
from collections import Counter
from pathlib import Path
from typing import Any


EVIDENCE_ID_RE = re.compile(r"\bP\d{2,4}-E\d{2,3}\b")


def load_review_payload(run_id: str, output_dir: Path, topic: str, status: str, error: str = "") -> dict[str, Any]:
    survey_path = output_dir / "survey.md"
    evidence_path = output_dir / "evidence_pack.json"
    check_path = output_dir / "check_report.json"
    trace_path = output_dir / "skill_trace.json"
    pdf_path = output_dir / "survey.pdf"

    markdown = survey_path.read_text(encoding="utf-8") if survey_path.exists() else ""
    evidence_pack = _read_json(evidence_path, {"papers": [], "evidence": []})
    check_report = _read_json(check_path, {"status": "not_run", "errors": [], "cited_evidence_ids": []})
    skill_trace = _read_json(trace_path, [])
    summary = build_summary(markdown, evidence_pack, check_report, skill_trace)

    return {
        "run_id": run_id,
        "topic": topic,
        "status": status,
        "error": error,
        "markdown": markdown,
        "summary": summary,
        "check_report": check_report,
        "downloads": {
            "markdown": f"/api/reviews/{run_id}/download/survey.md" if survey_path.exists() else "",
            "pdf": f"/api/reviews/{run_id}/download/survey.pdf" if pdf_path.exists() else "",
            "pdf_preview": f"/api/reviews/{run_id}/preview/survey.pdf" if pdf_path.exists() else "",
            "evidence": f"/api/reviews/{run_id}/download/evidence_pack.json" if evidence_path.exists() else "",
            "check_report": f"/api/reviews/{run_id}/download/check_report.json" if check_path.exists() else "",
            "skill_trace": f"/api/reviews/{run_id}/download/skill_trace.json" if trace_path.exists() else "",
        },
    }


def build_summary(
    markdown: str,
    evidence_pack: dict[str, Any],
    check_report: dict[str, Any],
    skill_trace: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    papers = [item for item in evidence_pack.get("papers", []) if isinstance(item, dict)]
    evidence = [item for item in evidence_pack.get("evidence", []) if isinstance(item, dict)]
    cited_ids = set(check_report.get("cited_evidence_ids") or EVIDENCE_ID_RE.findall(markdown))
    cited_paper_ids = {evidence_id.split("-E", 1)[0] for evidence_id in cited_ids}
    evidence_by_id = {str(item.get("evidence_id")): item for item in evidence}

    source_counts = Counter(str(item.get("source") or "unknown") for item in evidence)
    year_counts = Counter(str(item.get("year") or "Unknown") for item in evidence)
    mineru_counts = Counter(str((paper.get("mineru") or {}).get("state") or "not_submitted") for paper in papers)

    paper_rows = []
    for paper in papers[:80]:
        paper_id = str(paper.get("paper_id") or "")
        paper_rows.append(
            {
                "paper_id": paper_id,
                "title": str(paper.get("title") or "Untitled"),
                "year": paper.get("year"),
                "venue": paper.get("venue"),
                "evidence_count": len(paper.get("evidence_ids") or []),
                "cited": paper_id in cited_paper_ids,
                "mineru_state": str((paper.get("mineru") or {}).get("state") or "not_submitted"),
            }
        )

    cited_evidence = []
    for evidence_id in sorted(cited_ids):
        item = evidence_by_id.get(evidence_id)
        if not item:
            continue
        cited_evidence.append(
            {
                "evidence_id": evidence_id,
                "paper_id": item.get("paper_id"),
                "title": item.get("title"),
                "year": item.get("year"),
                "source": item.get("source"),
                "text": str(item.get("text") or "")[:700],
            }
        )

    return {
        "paper_count": len(papers),
        "evidence_count": len(evidence),
        "cited_evidence_count": len(cited_ids),
        "cited_paper_count": len(cited_paper_ids),
        "citation_status": check_report.get("status", "not_run"),
        "citation_errors": check_report.get("errors", []),
        "source_counts": _counter_rows(source_counts),
        "year_counts": _counter_rows(year_counts, numeric_labels=True),
        "mineru_counts": _counter_rows(mineru_counts),
        "paper_rows": paper_rows,
        "cited_evidence": cited_evidence[:80],
        "section_count": len(re.findall(r"^##\s+", markdown, flags=re.MULTILINE)),
        "word_count": len(re.findall(r"\b\w+\b", markdown)),
        "skill_trace": skill_trace or [],
    }


def _counter_rows(counter: Counter[str], *, numeric_labels: bool = False) -> list[dict[str, Any]]:
    rows = [{"label": key, "count": value} for key, value in counter.items()]
    if numeric_labels:
        return sorted(rows, key=lambda item: (item["label"] == "Unknown", str(item["label"])))
    return sorted(rows, key=lambda item: (-int(item["count"]), str(item["label"])))


def _read_json(path: Path, fallback: Any) -> Any:
    if not path.exists():
        return fallback
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return fallback
