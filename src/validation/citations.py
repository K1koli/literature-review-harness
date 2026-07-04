from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

from ..state.kb import LiteratureKB


EVIDENCE_ID_RE = re.compile(r"\bP\d{2,4}-E\d{2,3}\b")


@dataclass
class CitationReport:
    status: str
    errors: list[dict[str, Any]] = field(default_factory=list)
    warnings: list[dict[str, Any]] = field(default_factory=list)
    cited_evidence_ids: list[str] = field(default_factory=list)
    available_evidence_count: int = 0


class CitationVerifier:
    """Stop condition that rejects unknown evidence citations and uncited prose."""

    def __init__(self, kb: LiteratureKB) -> None:
        self.kb = kb
        self.last_report = CitationReport(status="not_run")

    def validate_text(self, text: str) -> CitationReport:
        known_ids = self.kb.evidence_ids()
        cited_ids = sorted(set(EVIDENCE_ID_RE.findall(text)))
        errors: list[dict[str, Any]] = []
        warnings: list[dict[str, Any]] = []
        for evidence_id in cited_ids:
            if evidence_id not in known_ids:
                errors.append({"issue": "unknown_evidence_id", "evidence_id": evidence_id})

        paragraphs = [part.strip() for part in re.split(r"\n\s*\n", text) if part.strip()]
        for index, paragraph in enumerate(paragraphs, start=1):
            if self._should_skip_paragraph(paragraph):
                continue
            if not EVIDENCE_ID_RE.search(paragraph):
                errors.append(
                    {
                        "issue": "missing_evidence_citation",
                        "paragraph": index,
                        "text": paragraph[:180],
                    }
                )

        status = "pass" if not errors else "fail"
        return CitationReport(
            status=status,
            errors=errors,
            warnings=warnings,
            cited_evidence_ids=cited_ids,
            available_evidence_count=len(known_ids),
        )

    def __call__(self, messages: list[dict[str, Any]]) -> bool:
        final = next((message for message in reversed(messages) if message.get("role") == "assistant" and message.get("content")), None)
        if final is None:
            self.last_report = CitationReport(status="fail", errors=[{"issue": "no_final_content"}])
            return False
        self.last_report = self.validate_text(str(final.get("content") or ""))
        if self.last_report.status != "pass":
            messages.append(
                {
                    "role": "user",
                    "content": (
                        "Citation verification failed. Revise the survey so every substantive paragraph "
                        "uses existing evidence ids such as P001-E01, and remove unknown citations. "
                        f"Errors: {self.last_report.errors[:8]}"
                    ),
                }
            )
        return self.last_report.status == "pass"

    @staticmethod
    def _should_skip_paragraph(paragraph: str) -> bool:
        stripped = paragraph.strip()
        if stripped.startswith("#"):
            return True
        if stripped.startswith("```"):
            return True
        if stripped.lower().startswith(("references", "参考文献")):
            return True
        if len(stripped) < 80:
            return True
        return False

    def report_dict(self) -> dict[str, Any]:
        return {
            "status": self.last_report.status,
            "errors": self.last_report.errors,
            "warnings": self.last_report.warnings,
            "cited_evidence_ids": self.last_report.cited_evidence_ids,
            "available_evidence_count": self.last_report.available_evidence_count,
        }
