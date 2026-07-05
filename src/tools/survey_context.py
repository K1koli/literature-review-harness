from __future__ import annotations

import json
import re
from typing import Any

from ..state.kb import EvidenceRecord, LiteratureKB, PaperRecord

ALLOWED_EVIDENCE_TOOLS = {
    "search_literature",
    "read_context",
    "list_parsed_papers",
    "read_parsed_paper",
    "search_parsed_paper",
}


class PrepareSurveyContextTool:
    name = "prepare_survey_context"
    description = (
        "Build a compact, evidence-grounded writing context from the current literature KB. "
        "Use after evidence collection and before writing the final survey. It prepares a deterministic "
        "timeline and citation map, then asks the configured LLM to design the survey outline. "
        "It does not write the survey."
    )
    parameters = {
        "type": "object",
        "properties": {
            "focus": {
                "type": "string",
                "description": "Optional writing focus, e.g. methods, applications, evaluation, open problems.",
                "default": "",
            },
            "max_evidence": {
                "type": "integer",
                "description": "Maximum evidence records to include in the writing context.",
                "default": 24,
            },
            "use_llm": {
                "type": "boolean",
                "description": "Use the configured LLM to design the survey outline, evidence needs, and writing plan.",
                "default": True,
            },
        },
    }

    def __init__(self, kb: LiteratureKB, llm: Any | None = None):
        self.kb = kb
        self.llm = llm

    async def execute(self, focus: str = "", max_evidence: int = 24, use_llm: bool = True) -> str:
        max_evidence = max(1, min(int(max_evidence or 24), 60))
        evidence = self.kb.evidence[:max_evidence]
        papers = [paper for paper in self.kb.papers if paper.evidence_ids]
        payload = {
            "purpose": (
                "Use this as writing context only. The final survey must still cite concrete evidence ids "
                "from citation_map and the KB in substantive paragraphs."
            ),
            "focus": focus,
            "coverage": _coverage(papers, evidence),
            "timeline": _timeline(papers),
            "citation_map": _citation_map(evidence),
            "outline_status": "llm_not_requested" if not use_llm else "llm_unavailable",
        }
        if use_llm and self.llm is not None:
            payload = await _add_llm_survey_design(self.llm, payload)
        return json.dumps(payload, ensure_ascii=False, indent=2)


async def _add_llm_survey_design(llm: Any, payload: dict[str, Any]) -> dict[str, Any]:
    compact = _compact_for_llm(payload)
    messages = [
        {
            "role": "system",
            "content": (
                "You design evidence-grounded academic survey structure. "
                "Use only the supplied paper/evidence ids. Do not write the survey. "
                "Return strict JSON only."
            ),
        },
        {
            "role": "user",
            "content": (
                "Given this literature evidence pack, design a better review plan. "
                "Filter weakly relevant material, identify missing evidence, and produce a publication-style outline.\n\n"
                "Return JSON with keys:\n"
                "- selected_papers: [{paper_id, reason}]\n"
                "- low_relevance_papers: [{paper_id, reason}]\n"
                "- evidence_needs: [{need, suggested_tools}]\n"
                "- recommended_outline: a non-empty array of 6-10 section titles, each with one concise purpose\n"
                "- writing_plan: concise guidance for final survey synthesis\n\n"
                "For evidence_needs.suggested_tools, use only harness tool names: "
                "search_literature, read_context, list_parsed_papers, read_parsed_paper, search_parsed_paper. "
                "Do not name external libraries or benchmarks as tools. "
                "Do not invent paper ids, evidence ids, authors, titles, venues, or results.\n\n"
                f"Evidence pack JSON:\n{json.dumps(compact, ensure_ascii=False)}"
            ),
        },
    ]
    try:
        response = await llm.chat(messages, tools=None)
        design = _parse_json_object(response.get("content", ""))
    except Exception as exc:
        payload["survey_design_error"] = str(exc)
        payload["outline_status"] = "llm_error"
        return payload

    if not isinstance(design, dict):
        payload["survey_design_error"] = "LLM did not return a JSON object."
        payload["outline_status"] = "llm_invalid_json"
        return payload

    design = _sanitize_design(design, payload)
    payload["survey_design"] = design
    outline = design.get("recommended_outline")
    if isinstance(outline, list) and outline:
        payload["recommended_outline"] = [str(item) for item in outline[:12]]
        payload["outline_status"] = "generated_by_llm"
    else:
        payload["outline_status"] = "llm_returned_no_outline"
    return payload


def _sanitize_design(design: dict[str, Any], payload: dict[str, Any]) -> dict[str, Any]:
    paper_ids = {
        paper.get("paper_id")
        for paper in payload.get("coverage", {}).get("papers", [])
        if isinstance(paper, dict)
    }

    sanitized = dict(design)
    sanitized["selected_papers"] = _filter_paper_rows(design.get("selected_papers"), paper_ids)
    sanitized["low_relevance_papers"] = _filter_paper_rows(design.get("low_relevance_papers"), paper_ids)
    sanitized["evidence_needs"] = _filter_evidence_needs(design.get("evidence_needs"))
    sanitized["recommended_outline"] = _filter_outline(_outline_rows(design))
    if not isinstance(sanitized.get("writing_plan"), str):
        sanitized["writing_plan"] = ""
    return sanitized


def _outline_rows(design: dict[str, Any]) -> Any:
    for key in ("recommended_outline", "outline", "review_outline", "sections", "section_plan"):
        rows = design.get(key)
        if isinstance(rows, list) and rows:
            return rows
    return []


def _filter_paper_rows(rows: Any, valid_paper_ids: set[str | None], max_rows: int = 30) -> list[dict[str, Any]]:
    if not isinstance(rows, list):
        return []
    filtered = []
    for row in rows:
        if not isinstance(row, dict) or row.get("paper_id") not in valid_paper_ids:
            continue
        filtered.append({key: row.get(key) for key in ("paper_id", "reason") if row.get(key)})
    return filtered[:max_rows]


def _filter_evidence_needs(rows: Any, max_rows: int = 8) -> list[dict[str, Any]]:
    if not isinstance(rows, list):
        return []
    filtered = []
    for row in rows:
        if not isinstance(row, dict) or not isinstance(row.get("need"), str):
            continue
        tools = [
            tool
            for tool in row.get("suggested_tools", [])
            if tool in ALLOWED_EVIDENCE_TOOLS
        ]
        filtered.append({"need": row["need"], "suggested_tools": tools})
    return filtered[:max_rows]


def _filter_outline(rows: Any, max_rows: int = 12) -> list[str]:
    if not isinstance(rows, list):
        return []
    outline = []
    for row in rows:
        if isinstance(row, dict):
            section = row.get("section") or row.get("title") or row.get("heading")
            purpose = row.get("purpose") or row.get("rationale") or row.get("description")
            if section and purpose:
                text = f"{section}: {purpose}"
            elif section:
                text = str(section)
            else:
                text = ""
        else:
            text = str(row)
        text = _short_phrase(text, max_chars=180)
        if text:
            outline.append(text)
    return outline[:max_rows]


def _compact_for_llm(payload: dict[str, Any]) -> dict[str, Any]:
    return {
        "focus": payload.get("focus"),
        "coverage": {
            **payload.get("coverage", {}),
            "papers": payload.get("coverage", {}).get("papers", [])[:30],
        },
        "timeline": payload.get("timeline", [])[:30],
        "citation_map": payload.get("citation_map", [])[:30],
    }


def _parse_json_object(text: str) -> dict[str, Any] | None:
    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned)
        cleaned = re.sub(r"\s*```$", "", cleaned)
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", cleaned, flags=re.DOTALL)
        if not match:
            return None
        try:
            return json.loads(match.group(0))
        except json.JSONDecodeError:
            return None


def _coverage(papers: list[PaperRecord], evidence: list[EvidenceRecord]) -> dict[str, Any]:
    years = sorted({paper.year for paper in papers if paper.year})
    return {
        "paper_count": len(papers),
        "evidence_count": len(evidence),
        "year_range": [years[0], years[-1]] if years else [],
        "papers": [
            {
                "paper_id": paper.paper_id,
                "title": paper.title,
                "year": paper.year,
                "venue": paper.venue,
                "evidence_ids": paper.evidence_ids[:6],
            }
            for paper in papers[:30]
        ],
    }


def _timeline(papers: list[PaperRecord]) -> list[dict[str, Any]]:
    rows = sorted((paper for paper in papers if paper.year), key=lambda item: (item.year or 0, item.paper_id))
    return [
        {
            "year": paper.year,
            "paper_id": paper.paper_id,
            "title": paper.title,
            "evidence_ids": paper.evidence_ids[:3],
        }
        for paper in rows[:30]
    ]


def _citation_map(evidence: list[EvidenceRecord]) -> list[dict[str, Any]]:
    return [
        {
            "claim_candidate": _claim_candidate(item.text),
            "evidence_id": item.evidence_id,
            "paper_id": item.paper_id,
            "title": item.title,
            "year": item.year,
        }
        for item in evidence[:36]
    ]


def _claim_candidate(text: str) -> str:
    sentence = _first_sentence(text)
    return _short_phrase(sentence, max_chars=220)


def _short_phrase(text: str, max_chars: int = 180) -> str:
    clean = re.sub(r"\s+", " ", text or "").strip()
    if len(clean) <= max_chars:
        return clean
    return clean[: max_chars - 3].rstrip() + "..."


def _first_sentence(text: str) -> str:
    match = re.search(r"(.+?[.!?])\s", text.strip())
    return match.group(1) if match else text
