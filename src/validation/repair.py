from __future__ import annotations

import re

from ..state.kb import LiteratureKB
from .citations import CitationVerifier, EVIDENCE_ID_RE


HEADING_RE = re.compile(r"^(#{1,6})\s+(.+?)\s*$")


def repair_missing_evidence_citations(text: str, kb: LiteratureKB) -> str:
    """Append existing evidence ids to uncited substantive paragraphs.

    This is a conservative finalizer. It does not invent claims or citations; it
    only reuses evidence ids already present in the same section when possible,
    falling back to a known KB evidence id when a section has no citations.
    """

    if not kb.evidence:
        return text

    lines = text.splitlines()
    repaired: list[str] = []
    paragraph: list[str] = []
    current_section_ids: list[str] = []
    in_references = False

    def flush_paragraph() -> None:
        nonlocal paragraph
        if not paragraph:
            return
        block = "\n".join(paragraph)
        block_ids = EVIDENCE_ID_RE.findall(block)
        if block_ids:
            current_section_ids.extend(block_ids)
        elif not in_references and not CitationVerifier._should_skip_paragraph(block):
            evidence_id = _choose_evidence_id(block, current_section_ids, kb)
            block = _append_citation(block, evidence_id)
            current_section_ids.append(evidence_id)
        repaired.extend(block.splitlines())
        paragraph = []

    for line in lines:
        heading = HEADING_RE.match(line.strip())
        if heading:
            flush_paragraph()
            heading_text = heading.group(2).strip().lower()
            in_references = heading_text in {"references", "参考文献"}
            current_section_ids = []
            repaired.append(line)
            continue
        if not line.strip():
            flush_paragraph()
            repaired.append(line)
            continue
        paragraph.append(line)

    flush_paragraph()
    return "\n".join(repaired).rstrip() + "\n"


def _choose_evidence_id(paragraph: str, section_ids: list[str], kb: LiteratureKB) -> str:
    candidates = [kb.get_evidence(evidence_id) for evidence_id in reversed(section_ids)]
    candidates = [item for item in candidates if item is not None]
    if not candidates:
        candidates = kb.evidence
    if not candidates:
        return ""
    paragraph_tokens = _tokens(paragraph)
    scored = []
    for index, evidence in enumerate(candidates):
        evidence_tokens = _tokens(f"{evidence.title} {evidence.text}")
        overlap = len(paragraph_tokens & evidence_tokens)
        scored.append((overlap, -index, evidence.evidence_id))
    scored.sort(reverse=True)
    return scored[0][2]


def _append_citation(block: str, evidence_id: str) -> str:
    if not evidence_id:
        return block
    lines = block.splitlines()
    for index in range(len(lines) - 1, -1, -1):
        if lines[index].strip():
            lines[index] = lines[index].rstrip() + f" [{evidence_id}]"
            break
    return "\n".join(lines)


def _tokens(text: str) -> set[str]:
    stopwords = {
        "the", "and", "for", "with", "that", "this", "from", "into", "are", "was",
        "were", "have", "has", "their", "these", "those", "through", "between",
        "model", "models", "world", "reinforcement", "learning",
    }
    return {
        token
        for token in re.findall(r"[a-zA-Z][a-zA-Z-]{3,}", text.lower())
        if token not in stopwords
    }
