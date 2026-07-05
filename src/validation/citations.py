from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

from ..state.kb import LiteratureKB


PAPER_ID_RE = re.compile(r"paper_id:\s*(P\d+)", re.IGNORECASE)


@dataclass
class CitationReport:
    status: str
    errors: list[dict[str, Any]] = field(default_factory=list)
    warnings: list[dict[str, Any]] = field(default_factory=list)
    cited_paper_ids: list[str] = field(default_factory=list)
    available_paper_count: int = 0


class CitationVerifier:
    """Stop condition that verifies References section paper_ids against the KB."""

    def __init__(self, kb: LiteratureKB) -> None:
        self.kb = kb
        self.last_report = CitationReport(status="not_run")

    def validate_text(self, text: str) -> CitationReport:
        known_ids = self.kb.paper_ids()
        cited_ids = sorted(set(PAPER_ID_RE.findall(text)))
        errors: list[dict[str, Any]] = []
        warnings: list[dict[str, Any]] = []

        lowered = text.lower()
        if "prompt processing error" in lowered or "error calling llm" in lowered:
            errors.append({"issue": "model_error_response", "text": text[:180]})

        if not known_ids:
            errors.append({"issue": "empty_evidence_kb", "message": "build_literature_kb must run before final survey"})

        for paper_id in cited_ids:
            if paper_id not in known_ids:
                errors.append({"issue": "unknown_paper_id", "paper_id": paper_id})

        # Detect duplicate paper_ids (same paper cited under different [N])
        all_ids = PAPER_ID_RE.findall(text)
        seen: dict[str, list[int]] = {}
        for i, pid in enumerate(all_ids, 1):
            seen.setdefault(pid, []).append(i)
        for pid, positions in seen.items():
            if len(positions) > 1:
                errors.append({"issue": "duplicate_paper_id", "paper_id": pid, "appears_at_positions": positions})

        status = "pass" if not errors else "fail"
        return CitationReport(
            status=status,
            errors=errors,
            warnings=warnings,
            cited_paper_ids=cited_ids,
            available_paper_count=len(known_ids),
        )

    def __call__(self, messages: list[dict[str, Any]]) -> bool:
        final = next((m for m in reversed(messages) if m.get("role") == "assistant" and m.get("content")), None)
        if final is None:
            self.last_report = CitationReport(status="fail", errors=[{"issue": "no_final_content"}])
            return False
        self.last_report = self.validate_text(str(final.get("content") or ""))
        if self.last_report.status != "pass":
            messages.append({
                "role": "user",
                "content": (
                    "Citation verification failed: some paper_ids in References do not exist in the KB. "
                    "Fix the References section — only include papers from search results with valid paper_ids. "
                    f"Errors: {self.last_report.errors[:8]}"
                ),
            })
        return self.last_report.status == "pass"

    def report_dict(self) -> dict[str, Any]:
        return {
            "status": self.last_report.status,
            "errors": self.last_report.errors,
            "warnings": self.last_report.warnings,
            "cited_paper_ids": self.last_report.cited_paper_ids,
            "available_paper_count": self.last_report.available_paper_count,
        }
