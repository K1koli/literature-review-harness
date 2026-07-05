from __future__ import annotations

import re

from ..state.kb import LiteratureKB, PaperRecord, normalize_title
from .citations import EVIDENCE_ID_RE


REFERENCE_HEADING_RE = re.compile(r"(?im)^#{1,6}\s+(references|参考文献)\s*$")
EVIDENCE_BRACKET_RE = re.compile(r"\[((?:\s*P\d{2,4}-E\d{2,3}\s*[,;]?\s*)+)\]")
REFERENCES_XML_RE = re.compile(r"\n?<references>.*?</references>\s*", re.IGNORECASE | re.DOTALL)
NUMBERED_SOURCE_RE = re.compile(r"Sources:\s*((?:\[[0-9,\s]+\]\s*[,;]?\s*)+)")
NUMBERED_SOURCE_GROUP_RE = re.compile(r"Sources:\s*\[([0-9,\s]+)\]")
CAPTION_SOURCE_RE = re.compile(
    r"\s+Sources:\s*(?:\[[0-9,\s]+\]|(?:P\d{2,4}-E\d{2,3}\s*[,;]?\s*)+)\.",
    re.IGNORECASE,
)
PAPER_ID_RE = re.compile(r"paper_id:\s*(P\d{2,4})", re.IGNORECASE)


def format_numbered_references(text: str, kb: LiteratureKB) -> str:
    """Render final reader-facing citations as numbered paper references.

    The agent and verifier work with fine-grained evidence ids. This finalizer
    keeps that audit trail in `check_report.json` while producing standard
    survey-style Markdown: inline numeric citations and one References entry
    per cited paper.
    """

    body = _body_without_references(text)
    body = REFERENCES_XML_RE.sub("\n", body).rstrip()
    if not kb.evidence or not EVIDENCE_ID_RE.search(body):
        return _normalize_existing_numbered_format(text, kb) + "\n"

    citation_index = _CitationIndex(kb)
    formatted = EVIDENCE_BRACKET_RE.sub(lambda match: citation_index.citation_for_ids(EVIDENCE_ID_RE.findall(match.group(1))), body)
    formatted = EVIDENCE_ID_RE.sub(lambda match: citation_index.citation_for_ids([match.group(0)]), formatted)
    formatted = _strip_caption_sources(_normalize_numbered_sources(formatted))
    references = citation_index.references_markdown()
    if references:
        formatted = formatted.rstrip() + "\n\n## References\n\n" + references + "\n"
    else:
        formatted = formatted.rstrip() + "\n"
    return formatted


def _body_without_references(text: str) -> str:
    match = REFERENCE_HEADING_RE.search(text)
    if not match:
        return text
    return text[: match.start()]


def _normalize_existing_numbered_format(text: str, kb: LiteratureKB) -> str:
    body = _body_without_references(text)
    body = REFERENCES_XML_RE.sub("\n", body).rstrip()
    body = _strip_caption_sources(_normalize_numbered_sources(body))
    reference_paper_ids = _existing_reference_paper_ids(text)
    if not reference_paper_ids:
        return body.rstrip()
    rows = []
    for index, paper_id in enumerate(reference_paper_ids, start=1):
        paper = kb.get_paper(paper_id)
        if paper is not None:
            rows.append(f"[{index}] {_format_reference(paper)}")
    if not rows:
        return body.rstrip()
    return body.rstrip() + "\n\n## References\n\n" + "\n".join(rows)


def _existing_reference_paper_ids(text: str) -> list[str]:
    match = REFERENCE_HEADING_RE.search(text)
    if not match:
        return []
    seen: set[str] = set()
    paper_ids: list[str] = []
    for paper_id in PAPER_ID_RE.findall(text[match.end() :]):
        if paper_id not in seen:
            seen.add(paper_id)
            paper_ids.append(paper_id)
    return paper_ids


def _normalize_numbered_sources(text: str) -> str:
    def replace(match: re.Match[str]) -> str:
        numbers = [int(value) for value in re.findall(r"\d+", match.group(1))]
        unique = []
        for number in sorted(numbers):
            if number not in unique:
                unique.append(number)
        return "Sources: [" + ", ".join(str(number) for number in unique) + "]"

    text = NUMBERED_SOURCE_RE.sub(replace, text)

    def replace_group(match: re.Match[str]) -> str:
        numbers = [int(value) for value in re.findall(r"\d+", match.group(1))]
        unique = []
        for number in sorted(numbers):
            if number not in unique:
                unique.append(number)
        return "Sources: [" + ", ".join(str(number) for number in unique) + "]"

    return NUMBERED_SOURCE_GROUP_RE.sub(replace_group, text)


def _strip_caption_sources(text: str) -> str:
    return CAPTION_SOURCE_RE.sub("", text)


class _CitationIndex:
    def __init__(self, kb: LiteratureKB) -> None:
        self.kb = kb
        self._key_to_number: dict[str, int] = {}
        self._key_to_paper: dict[str, PaperRecord] = {}

    def citation_for_ids(self, evidence_ids: list[str]) -> str:
        numbers: list[int] = []
        for evidence_id in evidence_ids:
            evidence = self.kb.get_evidence(evidence_id)
            if evidence is None:
                continue
            paper = self.kb.get_paper(evidence.paper_id)
            if paper is None:
                continue
            key = _reference_key(paper)
            if key not in self._key_to_number:
                self._key_to_number[key] = len(self._key_to_number) + 1
                self._key_to_paper[key] = paper
            number = self._key_to_number[key]
            if number not in numbers:
                numbers.append(number)
        if not numbers:
            return ""
        numbers.sort()
        return "[" + ", ".join(str(number) for number in numbers) + "]"

    def references_markdown(self) -> str:
        rows = sorted(self._key_to_number.items(), key=lambda item: item[1])
        return "\n".join(f"[{number}] {_format_reference(self._key_to_paper[key])}" for key, number in rows)


def _reference_key(paper: PaperRecord) -> str:
    normalized = normalize_title(paper.title)
    if normalized and normalized != "untitled":
        return f"title:{normalized}|year:{paper.year or ''}"
    return f"paper:{paper.paper_id}"


def _format_reference(paper: PaperRecord) -> str:
    parts: list[str] = []
    title = _sentence(paper.title or "Untitled")
    parts.append(title)
    authors = _format_authors(paper.authors)
    if authors:
        parts.append(_sentence(authors))
    if paper.year:
        parts.append(f"{paper.year}.")
    if paper.venue:
        parts.append(_sentence(paper.venue))
    if paper.doi:
        parts.append(f"doi: {paper.doi}.")
    parts.append(f"paper_id: {paper.paper_id}.")
    return " ".join(part for part in parts if part)


def _format_authors(authors: list[str]) -> str:
    clean = [_clean_author_name(author) for author in authors if isinstance(author, str)]
    clean = [author for author in clean if author]
    if not clean:
        return ""
    if len(clean) <= 6:
        return ", ".join(clean)
    return ", ".join(clean[:6]) + ", et al"


def _clean_author_name(author: str) -> str:
    clean = re.sub(r"\s+", " ", author).strip()
    if not clean:
        return ""
    # Some APIs return byte-code array strings such as "[[108 101 ...]]".
    # They are not reader-facing author names, so omit them from References.
    if re.fullmatch(r"[\[\]\d\s,;|.-]+", clean):
        return ""
    if clean.count("[") >= 2 and len(re.findall(r"\d{2,3}", clean)) >= 8:
        return ""
    return clean


def _sentence(text: str) -> str:
    clean = re.sub(r"\s+", " ", text).strip()
    if not clean:
        return ""
    return clean if clean.endswith((".", "?", "!")) else clean + "."
