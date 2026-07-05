from __future__ import annotations

import json
import re
from typing import Any

import httpx

from ..state.kb import EvidenceRecord, LiteratureKB, PaperRecord
from .mineru import MinerUConfig, run_mineru_for_kb


SCIVERSE_BASE = "https://api.sciverse.space"


def _safe_int(value: Any) -> int | None:
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return None


def _safe_float(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _nested_list(data: dict[str, Any], keys: list[str]) -> list[dict[str, Any]]:
    value: Any = data
    for key in keys:
        if not isinstance(value, dict):
            return []
        value = value.get(key)
    if isinstance(value, list):
        return [item for item in value if isinstance(item, dict)]
    return []


def _extract_items(data: dict[str, Any], primary: str) -> list[dict[str, Any]]:
    for path in [
        [primary],
        ["data", primary],
        ["data", "list"],
        ["data", "items"],
        ["data", "results"],
        ["result", primary],
    ]:
        items = _nested_list(data, path)
        if items:
            return items
    return []


def _authors(value: Any) -> list[str]:
    if isinstance(value, list):
        names = []
        for item in value:
            if isinstance(item, str):
                names.append(item)
            elif isinstance(item, dict) and item.get("name"):
                names.append(str(item["name"]))
        return names[:12]
    return []


def _arxiv_pdf_from_identifier(value: str | None) -> str | None:
    if not value:
        return None
    match = re.search(r"arxiv[.:/](\d{4}\.\d{4,5})(v\d+)?", value.lower())
    if not match:
        return None
    version = match.group(2) or ""
    return f"https://arxiv.org/pdf/{match.group(1)}{version}.pdf"


def _normalize_arxiv_pdf(url: str) -> str:
    if "arxiv.org/pdf/" in url.lower() and not url.lower().endswith(".pdf"):
        return url.rstrip("/") + ".pdf"
    return url


def _parse_url_from_metadata(metadata: dict[str, Any]) -> str | None:
    urls: list[str] = []
    for key in ["access_oa_url", "pdf_url", "open_access_url", "url"]:
        value = metadata.get(key)
        if isinstance(value, list):
            urls.extend(str(item) for item in value if item)
        elif value:
            urls.append(str(value))
    locations = metadata.get("locations")
    if isinstance(locations, list):
        for item in locations:
            if isinstance(item, dict) and item.get("url"):
                urls.append(str(item["url"]))
    for key in ["doi", "unique_id"]:
        derived = _arxiv_pdf_from_identifier(str(metadata.get(key) or ""))
        if derived:
            urls.append(derived)
    ranked = []
    for url in urls:
        normalized = _normalize_arxiv_pdf(url.strip())
        lowered = normalized.lower()
        score = 0
        if "arxiv.org/pdf/" in lowered or lowered.endswith(".pdf"):
            score += 50
        if lowered.endswith((".html", ".htm")):
            score += 15
        if "doi.org/" in lowered:
            score -= 40
        if score > 0:
            ranked.append((score, normalized))
    return sorted(ranked, reverse=True)[0][1] if ranked else None


def _metadata_from_hit(hit: dict[str, Any]) -> dict[str, Any]:
    metadata = dict(hit.get("metadata") or hit.get("paper") or {})
    for source_key, target_key in [
        ("title", "title"),
        ("abstract", "abstract"),
        ("doc_id", "doc_id"),
        ("doi", "doi"),
        ("publication_published_year", "publication_published_year"),
        ("year", "publication_published_year"),
        ("publication_venue_name_unified", "publication_venue_name_unified"),
        ("venue", "publication_venue_name_unified"),
        ("author", "author"),
        ("authors", "author"),
        ("access_oa_url", "access_oa_url"),
        ("locations", "locations"),
    ]:
        if source_key in hit and target_key not in metadata:
            metadata[target_key] = hit[source_key]
    return metadata


def _paper_from_metadata(kb: LiteratureKB, metadata: dict[str, Any]) -> PaperRecord:
    title = str(metadata.get("title") or "Untitled")
    return kb.upsert_paper(
        title=title,
        year=_safe_int(metadata.get("publication_published_year") or metadata.get("year")),
        venue=metadata.get("publication_venue_name_unified") or metadata.get("venue"),
        doi=str(metadata.get("doi")) if metadata.get("doi") else None,
        authors=_authors(metadata.get("author") or metadata.get("authors")),
        doc_id=str(metadata.get("doc_id")) if metadata.get("doc_id") else None,
        parse_url=_parse_url_from_metadata(metadata),
    )


def _evidence_summary(item: EvidenceRecord) -> dict[str, Any]:
    return {
        "evidence_id": item.evidence_id,
        "paper_id": item.paper_id,
        "title": item.title,
        "year": item.year,
        "source": item.source,
        "doc_id": item.doc_id,
        "offset": item.offset,
        "score": item.score,
        "text": item.text[:500],
    }


class SciverseClient:
    def __init__(self, api_token: str) -> None:
        self._headers = {"Authorization": f"Bearer {api_token}", "Content-Type": "application/json"}

    async def semantic_search(self, query: str, *, top_k: int) -> list[dict[str, Any]]:
        async with httpx.AsyncClient(timeout=60) as client:
            response = await client.post(
                f"{SCIVERSE_BASE}/agentic-search",
                headers=self._headers,
                json={"query": query, "top_k": min(max(top_k, 1), 30), "mode": "balanced"},
            )
            response.raise_for_status()
            return _extract_items(response.json(), "hits")

    async def meta_search(self, query: str, *, page_size: int) -> list[dict[str, Any]]:
        async with httpx.AsyncClient(timeout=60) as client:
            response = await client.post(
                f"{SCIVERSE_BASE}/meta-search",
                headers=self._headers,
                json={"query": query, "page_size": min(max(page_size, 1), 50), "freshness_boost": "MILD"},
            )
            response.raise_for_status()
            return _extract_items(response.json(), "results")

    async def read_content(self, doc_id: str, *, offset: int, limit: int) -> dict[str, Any]:
        async with httpx.AsyncClient(timeout=60) as client:
            response = await client.get(
                f"{SCIVERSE_BASE}/content",
                headers=self._headers,
                params={"doc_id": doc_id, "offset": max(offset, 0), "limit": min(max(limit, 1), 8192)},
            )
            response.raise_for_status()
            return response.json()


class BuildLiteratureKBTool:
    name = "build_literature_kb"
    description = (
        "Build a source-backed literature evidence KB for the review topic. "
        "Uses Sciverse semantic/meta search and opportunistic MinerU parsing. "
        "Call this before writing the survey."
    )
    parameters = {
        "type": "object",
        "properties": {
            "query": {"type": "string", "description": "Review topic or retrieval query."},
            "top_k": {"type": "integer", "default": 50, "description": "Semantic result count."},
            "max_papers": {"type": "integer", "default": 50, "description": "Maximum papers to keep."},
            "use_mineru": {"type": "boolean", "default": True, "description": "Whether to try MinerU parsing."},
        },
        "required": ["query"],
    }

    def __init__(self, sciverse_token: str, kb: LiteratureKB, mineru_config: MinerUConfig):
        self.sciverse = SciverseClient(sciverse_token)
        self.kb = kb
        self.mineru_config = mineru_config

    async def execute(self, query: str, top_k: int = 50, max_papers: int = 50, use_mineru: bool = True) -> str:
        hits = await self.sciverse.semantic_search(query, top_k=top_k)
        meta_results: list[dict[str, Any]] = []
        try:
            meta_results = await self.sciverse.meta_search(query, page_size=max_papers)
        except Exception:
            meta_results = []

        for hit in hits:
            metadata = _metadata_from_hit(hit)
            paper = _paper_from_metadata(self.kb, metadata)
            chunk = hit.get("chunk") or hit.get("text") or hit.get("snippet") or ""
            self.kb.add_evidence(
                paper,
                text=str(chunk),
                source="sciverse_semantic",
                doc_id=hit.get("doc_id") or metadata.get("doc_id"),
                offset=_safe_int(hit.get("offset")),
                score=_safe_float(hit.get("score")),
            )

        for item in meta_results:
            paper = _paper_from_metadata(self.kb, item)
            abstract = str(item.get("abstract") or "").strip()
            if len(abstract.split()) >= 20:
                self.kb.add_evidence(
                    paper,
                    text=abstract,
                    source="sciverse_metadata_abstract",
                    doc_id=item.get("doc_id"),
                    score=_safe_float(item.get("relevance_score")),
                )

        # Keep the first max_papers records by insertion order and rebuild KB indexes.
        self.kb.keep_first_papers(max_papers)

        mineru_report = {"enabled": False}
        if use_mineru:
            mineru_report = await run_mineru_for_kb(self.kb, self.mineru_config)

        return json.dumps(
            {
                "papers": len(self.kb.papers),
                "evidence": len(self.kb.evidence),
                "mineru": mineru_report,
                "sample_evidence": [_evidence_summary(item) for item in self.kb.evidence[:10]],
            },
            ensure_ascii=False,
            indent=2,
        )


class SearchLiteratureTool:
    name = "search_literature"
    description = (
        "Search Sciverse and add returned snippets as evidence records in the shared KB. "
        "Returns stable evidence ids that must be used for citations."
    )
    parameters = {
        "type": "object",
        "properties": {
            "query": {"type": "string", "description": "Natural language literature search query."},
            "top_k": {"type": "integer", "description": "Number of results to return.", "default": 20},
        },
        "required": ["query"],
    }

    def __init__(self, api_token: str, kb: LiteratureKB):
        self.sciverse = SciverseClient(api_token)
        self.kb = kb

    async def execute(self, query: str, top_k: int = 20) -> str:
        hits = await self.sciverse.semantic_search(query, top_k=top_k)
        evidence: list[EvidenceRecord] = []
        for hit in hits:
            metadata = _metadata_from_hit(hit)
            paper = _paper_from_metadata(self.kb, metadata)
            item = self.kb.add_evidence(
                paper,
                text=str(hit.get("chunk") or hit.get("text") or hit.get("snippet") or ""),
                source="sciverse_semantic",
                doc_id=hit.get("doc_id") or metadata.get("doc_id"),
                offset=_safe_int(hit.get("offset")),
                score=_safe_float(hit.get("score")),
            )
            if item:
                evidence.append(item)
        return json.dumps([_evidence_summary(item) for item in evidence], ensure_ascii=False, indent=2)


class ReadContextTool:
    name = "read_context"
    description = "Read Sciverse context and add it as a citeable evidence record."
    parameters = {
        "type": "object",
        "properties": {
            "doc_id": {"type": "string", "description": "Document id from Sciverse evidence."},
            "offset": {"type": "integer", "default": 0},
            "limit": {"type": "integer", "default": 3000},
        },
        "required": ["doc_id"],
    }

    def __init__(self, api_token: str, kb: LiteratureKB):
        self.sciverse = SciverseClient(api_token)
        self.kb = kb

    async def execute(self, doc_id: str, offset: int = 0, limit: int = 3000) -> str:
        data = await self.sciverse.read_content(doc_id, offset=offset, limit=limit)
        paper = self.kb.find_by_doc_id(doc_id) or self.kb.upsert_paper(title=f"Sciverse document {doc_id}", doc_id=doc_id)
        evidence = self.kb.add_evidence(
            paper,
            text=str(data.get("text") or ""),
            source="sciverse_context",
            doc_id=doc_id,
            offset=offset,
        )
        return json.dumps(
            {
                "evidence": _evidence_summary(evidence) if evidence else None,
                "more": data.get("more", False),
                "next_offset": data.get("next_offset"),
            },
            ensure_ascii=False,
            indent=2,
        )


class ListEvidenceTool:
    name = "list_evidence"
    description = "List evidence records currently available in the literature KB."
    parameters = {
        "type": "object",
        "properties": {
            "limit": {"type": "integer", "default": 30},
            "source": {"type": "string", "description": "Optional source filter."},
        },
    }

    def __init__(self, kb: LiteratureKB):
        self.kb = kb

    async def execute(self, limit: int = 30, source: str | None = None) -> str:
        rows = [item for item in self.kb.evidence if not source or item.source == source]
        return json.dumps([_evidence_summary(item) for item in rows[:limit]], ensure_ascii=False, indent=2)


class ReadEvidenceTool:
    name = "read_evidence"
    description = "Read one full evidence record by evidence id."
    parameters = {
        "type": "object",
        "properties": {"evidence_id": {"type": "string", "description": "Evidence id such as P001-E01."}},
        "required": ["evidence_id"],
    }

    def __init__(self, kb: LiteratureKB):
        self.kb = kb

    async def execute(self, evidence_id: str) -> str:
        item = self.kb.get_evidence(evidence_id)
        if item is None:
            return f"Error: evidence_id {evidence_id} not found."
        return json.dumps(_evidence_summary(item) | {"text": item.text}, ensure_ascii=False, indent=2)


class ListParsedPapersTool:
    name = "list_parsed_papers"
    description = (
        "List papers with available MinerU parsed full-text documents. "
        "Use this when Sciverse snippets are too thin and you need to inspect parsed original text."
    )
    parameters = {"type": "object", "properties": {}}

    def __init__(self, kb: LiteratureKB):
        self.kb = kb

    async def execute(self) -> str:
        return json.dumps(self.kb.parsed_document_summaries(), ensure_ascii=False, indent=2)


class ReadParsedPaperTool:
    name = "read_parsed_paper"
    description = (
        "Read a chunk from a MinerU parsed paper by paper_id and add the returned chunk as citeable evidence. "
        "Use offsets to continue reading if needed."
    )
    parameters = {
        "type": "object",
        "properties": {
            "paper_id": {"type": "string", "description": "Paper id such as P001."},
            "offset": {"type": "integer", "default": 0, "description": "Character offset in parsed text."},
            "limit": {"type": "integer", "default": 3000, "description": "Characters to return, capped at 6000."},
        },
        "required": ["paper_id"],
    }

    def __init__(self, kb: LiteratureKB):
        self.kb = kb

    async def execute(self, paper_id: str, offset: int = 0, limit: int = 3000) -> str:
        document = self.kb.get_parsed_document(paper_id)
        paper = self.kb.get_paper(paper_id)
        if document is None or paper is None:
            return f"Error: parsed document for {paper_id} not found. Call list_parsed_papers to inspect available documents."
        start = max(offset, 0)
        size = min(max(limit, 1), 6000)
        text = document.text[start : start + size]
        evidence = self.kb.add_evidence(
            paper,
            text=text,
            source="mineru_parsed_read",
            offset=start,
        )
        return json.dumps(
            {
                "paper_id": paper_id,
                "title": document.title,
                "offset": start,
                "limit": size,
                "more": start + size < len(document.text),
                "next_offset": start + size if start + size < len(document.text) else None,
                "evidence": _evidence_summary(evidence) if evidence else None,
                "text": text,
            },
            ensure_ascii=False,
            indent=2,
        )


class SearchParsedPaperTool:
    name = "search_parsed_paper"
    description = (
        "Search MinerU parsed paper text by keyword query and add matching snippets as citeable evidence. "
        "Use this to find original-paper support for specific claims, limitations, evaluations, or methods."
    )
    parameters = {
        "type": "object",
        "properties": {
            "paper_id": {"type": "string", "description": "Paper id such as P001."},
            "query": {"type": "string", "description": "Keyword query to search inside the parsed paper."},
            "max_hits": {"type": "integer", "default": 3, "description": "Maximum matching snippets."},
        },
        "required": ["paper_id", "query"],
    }

    def __init__(self, kb: LiteratureKB):
        self.kb = kb

    async def execute(self, paper_id: str, query: str, max_hits: int = 3) -> str:
        document = self.kb.get_parsed_document(paper_id)
        paper = self.kb.get_paper(paper_id)
        if document is None or paper is None:
            return f"Error: parsed document for {paper_id} not found. Call list_parsed_papers to inspect available documents."
        terms = [term for term in re.findall(r"[A-Za-z0-9][A-Za-z0-9_-]{2,}", query.lower()) if len(term) >= 3]
        if not terms:
            return "Error: query must contain at least one searchable term."
        matches: list[dict[str, Any]] = []
        lowered = document.text.lower()
        seen_offsets: set[int] = set()
        for term in terms:
            start = 0
            while len(matches) < max(1, min(max_hits, 8)):
                index = lowered.find(term, start)
                if index < 0:
                    break
                snippet_start = max(index - 700, 0)
                if any(abs(snippet_start - existing) < 300 for existing in seen_offsets):
                    start = index + len(term)
                    continue
                seen_offsets.add(snippet_start)
                snippet = document.text[snippet_start : snippet_start + 1400]
                evidence = self.kb.add_evidence(
                    paper,
                    text=snippet,
                    source="mineru_parsed_search",
                    offset=snippet_start,
                )
                matches.append(
                    {
                        "term": term,
                        "offset": snippet_start,
                        "evidence": _evidence_summary(evidence) if evidence else None,
                        "text": snippet,
                    }
                )
                start = index + len(term)
        return json.dumps(
            {
                "paper_id": paper_id,
                "title": document.title,
                "query": query,
                "matches": matches,
            },
            ensure_ascii=False,
            indent=2,
        )
