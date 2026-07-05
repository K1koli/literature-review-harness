from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass, field
from typing import Any


def normalize_title(title: str | None) -> str:
    return re.sub(r"\s+", " ", (title or "").strip()).lower()


@dataclass
class PaperRecord:
    paper_id: str
    title: str
    year: int | None = None
    venue: str | None = None
    doi: str | None = None
    authors: list[str] = field(default_factory=list)
    doc_id: str | None = None
    parse_url: str | None = None
    mineru: dict[str, Any] = field(default_factory=dict)
    evidence_ids: list[str] = field(default_factory=list)


@dataclass
class EvidenceRecord:
    evidence_id: str
    paper_id: str
    title: str
    text: str
    source: str
    doc_id: str | None = None
    offset: int | None = None
    score: float | None = None
    year: int | None = None


@dataclass
class ParsedDocument:
    paper_id: str
    title: str
    text: str
    source: str
    metadata: dict[str, Any] = field(default_factory=dict)


class LiteratureKB:
    """Runtime evidence KB shared across agent tools."""

    def __init__(self) -> None:
        self.papers: list[PaperRecord] = []
        self.evidence: list[EvidenceRecord] = []
        self.parsed_documents: dict[str, ParsedDocument] = {}
        self._paper_by_key: dict[str, PaperRecord] = {}
        self._paper_by_id: dict[str, PaperRecord] = {}
        self._paper_by_doc_id: dict[str, PaperRecord] = {}

    def _rebuild_indexes(self) -> None:
        self._paper_by_key = {}
        self._paper_by_id = {}
        self._paper_by_doc_id = {}
        for paper in self.papers:
            self._paper_by_id[paper.paper_id] = paper
            if paper.doc_id:
                self._paper_by_doc_id[paper.doc_id] = paper
            for key in self._keys_for(title=paper.title, doi=paper.doi, doc_id=paper.doc_id):
                self._paper_by_key[key] = paper

    def _keys_for(self, *, title: str | None, doi: str | None, doc_id: str | None) -> list[str]:
        keys: list[str] = []
        if doi:
            keys.append(f"doi:{doi.lower()}")
        if doc_id:
            keys.append(f"doc:{doc_id}")
        norm_title = normalize_title(title)
        if norm_title:
            keys.append(f"title:{norm_title}")
        return keys

    def upsert_paper(
        self,
        *,
        title: str,
        year: int | None = None,
        venue: str | None = None,
        doi: str | None = None,
        authors: list[str] | None = None,
        doc_id: str | None = None,
        parse_url: str | None = None,
    ) -> PaperRecord:
        keys = self._keys_for(title=title, doi=doi, doc_id=doc_id)
        paper = next((self._paper_by_key[key] for key in keys if key in self._paper_by_key), None)
        if paper is None:
            paper = PaperRecord(paper_id=f"P{len(self.papers) + 1:03d}", title=title or "Untitled")
            self.papers.append(paper)
            self._paper_by_id[paper.paper_id] = paper

        paper.title = paper.title if paper.title != "Untitled" else title or paper.title
        paper.year = paper.year or year
        paper.venue = paper.venue or venue
        paper.doi = paper.doi or doi
        paper.doc_id = paper.doc_id or doc_id
        paper.parse_url = paper.parse_url or parse_url
        if authors and not paper.authors:
            paper.authors = authors
        if paper.doc_id:
            self._paper_by_doc_id[paper.doc_id] = paper
        for key in self._keys_for(title=paper.title, doi=paper.doi, doc_id=paper.doc_id):
            self._paper_by_key[key] = paper
        return paper

    def find_by_doc_id(self, doc_id: str) -> PaperRecord | None:
        return self._paper_by_doc_id.get(doc_id)

    def add_evidence(
        self,
        paper: PaperRecord,
        *,
        text: str,
        source: str,
        doc_id: str | None = None,
        offset: int | None = None,
        score: float | None = None,
    ) -> EvidenceRecord | None:
        clean_text = re.sub(r"\s+", " ", text or "").strip()
        if not clean_text:
            return None
        evidence_number = len(paper.evidence_ids) + 1
        evidence = EvidenceRecord(
            evidence_id=f"{paper.paper_id}-E{evidence_number:02d}",
            paper_id=paper.paper_id,
            title=paper.title,
            text=clean_text[:1600],
            source=source,
            doc_id=doc_id or paper.doc_id,
            offset=offset,
            score=score,
            year=paper.year,
        )
        self.evidence.append(evidence)
        paper.evidence_ids.append(evidence.evidence_id)
        return evidence

    def get_evidence(self, evidence_id: str) -> EvidenceRecord | None:
        return next((item for item in self.evidence if item.evidence_id == evidence_id), None)

    def get_paper(self, paper_id: str) -> PaperRecord | None:
        return self._paper_by_id.get(paper_id)

    def set_parsed_document(
        self,
        paper: PaperRecord,
        *,
        text: str,
        source: str,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        clean_text = re.sub(r"\n{3,}", "\n\n", text or "").strip()
        if not clean_text:
            return
        self.parsed_documents[paper.paper_id] = ParsedDocument(
            paper_id=paper.paper_id,
            title=paper.title,
            text=clean_text,
            source=source,
            metadata=metadata or {},
        )

    def get_parsed_document(self, paper_id: str) -> ParsedDocument | None:
        return self.parsed_documents.get(paper_id)

    def parsed_document_summaries(self) -> list[dict[str, Any]]:
        return [
            {
                "paper_id": document.paper_id,
                "title": document.title,
                "source": document.source,
                "characters": len(document.text),
                "metadata": document.metadata,
                "preview": document.text[:300],
            }
            for document in self.parsed_documents.values()
        ]

    def set_mineru_state(self, paper: PaperRecord, state: dict[str, Any]) -> None:
        paper.mineru.update(state)

    def keep_first_papers(self, max_count: int) -> None:
        if max_count <= 0:
            self.papers = []
            self.evidence = []
            self.parsed_documents = {}
            self._rebuild_indexes()
            return
        if len(self.papers) <= max_count:
            return
        kept_ids = {paper.paper_id for paper in self.papers[:max_count]}
        self.papers = self.papers[:max_count]
        self.evidence = [item for item in self.evidence if item.paper_id in kept_ids]
        self.parsed_documents = {
            paper_id: document
            for paper_id, document in self.parsed_documents.items()
            if paper_id in kept_ids
        }
        evidence_by_paper: dict[str, list[str]] = {paper.paper_id: [] for paper in self.papers}
        for item in self.evidence:
            evidence_by_paper.setdefault(item.paper_id, []).append(item.evidence_id)
        for paper in self.papers:
            paper.evidence_ids = evidence_by_paper.get(paper.paper_id, [])
        self._rebuild_indexes()

    def evidence_ids(self) -> set[str]:
        return {item.evidence_id for item in self.evidence}

    def to_dict(self) -> dict[str, Any]:
        return {
            "papers": [asdict(paper) for paper in self.papers],
            "evidence": [asdict(item) for item in self.evidence],
            "parsed_documents": self.parsed_document_summaries(),
        }

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), ensure_ascii=False, indent=2)
