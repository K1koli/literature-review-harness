from __future__ import annotations

import io
import json
import re
import time
import zipfile
from dataclasses import dataclass
from typing import Any

import httpx

from ..state.kb import LiteratureKB, PaperRecord


MINERU_BASE = "https://mineru.net"
MINERU_DONE_STATES = {"done", "failed"}
MINERU_FAST_PAGE_RANGES = "1-12"


@dataclass
class MinerUConfig:
    api_token: str = ""
    enabled: bool = True
    timeout_seconds: int = 600
    poll_interval_seconds: int = 30
    batch_size: int = 1
    model_version: str = "pipeline"
    language: str = "en"
    page_ranges: str = MINERU_FAST_PAGE_RANGES
    enable_table: bool = False
    enable_formula: bool = False
    is_ocr: bool = False
    no_cache: bool = False
    evidence_per_paper: int = 2


def is_parseable_url(url: str | None) -> bool:
    if not url:
        return False
    lowered = url.lower()
    return any(
        marker in lowered
        for marker in [
            "arxiv.org/pdf/",
            ".pdf",
            ".html",
            ".htm",
            ".doc",
            ".docx",
            ".ppt",
            ".pptx",
        ]
    )


def model_for_url(url: str, default_model: str) -> str:
    path = url.lower().split("?", 1)[0]
    if path.endswith((".html", ".htm")):
        return "MinerU-HTML"
    return default_model


def _chunked(items: list[dict[str, Any]], size: int) -> list[list[dict[str, Any]]]:
    size = max(1, size)
    return [items[index : index + size] for index in range(0, len(items), size)]


class MinerUClient:
    def __init__(self, token: str) -> None:
        self._headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}

    async def submit_url_batch(
        self,
        files: list[dict[str, str]],
        *,
        config: MinerUConfig,
        model_version: str,
    ) -> dict[str, Any]:
        payload_files = []
        for item in files:
            file_payload: dict[str, Any] = {"url": item["url"], "data_id": item["data_id"]}
            if config.page_ranges:
                file_payload["page_ranges"] = config.page_ranges
            payload_files.append(file_payload)
        payload = {
            "files": payload_files,
            "model_version": model_version,
            "language": config.language,
            "enable_table": config.enable_table,
            "enable_formula": config.enable_formula,
            "is_ocr": config.is_ocr,
            "no_cache": config.no_cache,
        }
        async with httpx.AsyncClient(timeout=120) as client:
            response = await client.post(
                f"{MINERU_BASE}/api/v4/extract/task/batch",
                headers=self._headers,
                json=payload,
            )
            response.raise_for_status()
            return response.json()

    async def get_batch_result(self, batch_id: str) -> dict[str, Any]:
        async with httpx.AsyncClient(timeout=120) as client:
            response = await client.get(
                f"{MINERU_BASE}/api/v4/extract-results/batch/{batch_id}",
                headers=self._headers,
            )
            response.raise_for_status()
            return response.json()

    async def download_zip(self, url: str) -> bytes:
        async with httpx.AsyncClient(timeout=180) as client:
            response = await client.get(url)
            response.raise_for_status()
            return response.content


def _safe_zip_json(zip_bytes: bytes) -> dict[str, Any] | None:
    with zipfile.ZipFile(io.BytesIO(zip_bytes)) as archive:
        candidates = [
            item for item in archive.namelist()
            if item.endswith("content_list.json") or item.endswith("content_list_v2.json")
        ]
        if candidates:
            with archive.open(sorted(candidates)[0]) as handle:
                content_list = json.loads(handle.read().decode("utf-8"))
            return {"content_list": content_list}
        markdown_candidates = [item for item in archive.namelist() if item.endswith("full.md")]
        if markdown_candidates:
            with archive.open(sorted(markdown_candidates)[0]) as handle:
                markdown = handle.read().decode("utf-8", errors="ignore")
            content_list = [
                {"type": "text", "text": paragraph.strip()}
                for paragraph in re.split(r"\n\s*\n", markdown)
                if paragraph.strip()
            ]
            return {"content_list": content_list, "markdown_path": sorted(markdown_candidates)[0]}
    return None


def _block_text(block: dict[str, Any]) -> str:
    text = block.get("text")
    if isinstance(text, str):
        return text
    for key in ["caption", "table_caption", "image_caption"]:
        value = block.get(key)
        if isinstance(value, str):
            return value
        if isinstance(value, list):
            return " ".join(str(item) for item in value)
    return ""


def mineru_evidence_chunks(structured: dict[str, Any], *, max_items: int) -> list[str]:
    content = structured.get("content_list") or []
    chunks: list[str] = []
    buffer: list[str] = []
    for block in content:
        if not isinstance(block, dict):
            continue
        text = re.sub(r"\s+", " ", _block_text(block)).strip()
        if not text:
            continue
        lowered = text.lower()
        if lowered in {"references", "bibliography"} or "参考文献" in text:
            break
        buffer.append(text)
        if sum(len(item) for item in buffer) >= 900:
            chunks.append(" ".join(buffer)[:1400])
            buffer = []
        if len(chunks) >= max_items:
            break
    if buffer and len(chunks) < max_items:
        chunks.append(" ".join(buffer)[:1400])
    return [chunk for chunk in chunks if len(chunk.split()) >= 20]


async def run_mineru_for_kb(kb: LiteratureKB, config: MinerUConfig) -> dict[str, Any]:
    """Submit parseable papers to MinerU and add completed structured evidence.

    MinerU is opportunistic: failures and timeouts leave Sciverse evidence intact.
    """

    if not config.enabled or not config.api_token:
        for paper in kb.papers:
            kb.set_mineru_state(paper, {"state": "skipped", "reason": "MinerU disabled or missing token"})
        return {"enabled": False, "submitted": 0, "done": 0, "failed": 0, "skipped": len(kb.papers)}

    parseable: list[tuple[PaperRecord, str]] = [
        (paper, paper.parse_url or "")
        for paper in kb.papers
        if is_parseable_url(paper.parse_url)
    ]
    parseable_ids = {paper.paper_id for paper, _ in parseable}
    for paper in kb.papers:
        if paper.paper_id not in parseable_ids:
            kb.set_mineru_state(paper, {"state": "skipped", "reason": "No parseable URL; using Sciverse evidence"})
    if not parseable:
        return {"enabled": True, "submitted": 0, "done": 0, "failed": 0, "skipped": len(kb.papers)}

    client = MinerUClient(config.api_token)
    batches: list[dict[str, Any]] = []
    paper_by_data_id: dict[str, PaperRecord] = {}
    work_items: list[dict[str, str]] = []
    for paper, url in parseable:
        data_id = paper.paper_id
        paper_by_data_id[data_id] = paper
        work_items.append({"data_id": data_id, "url": url, "model_version": model_for_url(url, config.model_version)})
        kb.set_mineru_state(paper, {"state": "queued", "data_id": data_id, "parse_url": url})

    for group_model in sorted({item["model_version"] for item in work_items}):
        model_items = [item for item in work_items if item["model_version"] == group_model]
        for group in _chunked(model_items, config.batch_size):
            try:
                submitted = await client.submit_url_batch(
                    [{"url": item["url"], "data_id": item["data_id"]} for item in group],
                    config=config,
                    model_version=group_model,
                )
                batch_id = (submitted.get("data") or {}).get("batch_id")
            except Exception as exc:
                batch_id = None
                submitted = {"error": str(exc)}
            for item in group:
                paper = paper_by_data_id[item["data_id"]]
                kb.set_mineru_state(paper, {"state": "submitted" if batch_id else "failed", "batch_id": batch_id, "submit_response": submitted})
            if batch_id:
                batches.append({"batch_id": batch_id, "items": group})

    deadline = time.time() + max(config.timeout_seconds, 0)
    active = batches
    while active and time.time() < deadline:
        next_active: list[dict[str, Any]] = []
        for batch in active:
            try:
                result = await client.get_batch_result(str(batch["batch_id"]))
            except Exception as exc:
                result = {"error": str(exc), "data": {"extract_result": []}}
            result_items = (result.get("data") or {}).get("extract_result") or []
            terminal_ids: set[str] = set()
            for result_item in result_items:
                if not isinstance(result_item, dict):
                    continue
                data_id = str(result_item.get("data_id") or "")
                paper = paper_by_data_id.get(data_id)
                if paper is None:
                    continue
                state = str(result_item.get("state") or "unknown")
                kb.set_mineru_state(paper, {"state": state, "batch_result": result_item})
                if state == "done" and result_item.get("full_zip_url") and not paper.mineru.get("structured_ingested"):
                    try:
                        zip_bytes = await client.download_zip(str(result_item["full_zip_url"]))
                        structured = _safe_zip_json(zip_bytes)
                        if structured:
                            for chunk in mineru_evidence_chunks(structured, max_items=config.evidence_per_paper):
                                kb.add_evidence(paper, text=chunk, source="mineru_structured")
                            kb.set_mineru_state(
                                paper,
                                {
                                    "full_zip_url": result_item["full_zip_url"],
                                    "structured_ingested": True,
                                },
                            )
                    except Exception as exc:
                        kb.set_mineru_state(paper, {"state": "failed", "error": str(exc)})
                        state = "failed"
                if state in MINERU_DONE_STATES:
                    terminal_ids.add(data_id)
            expected_ids = {str(item["data_id"]) for item in batch["items"]}
            local_terminal_ids = {
                data_id
                for data_id in expected_ids
                if paper_by_data_id[data_id].mineru.get("state") in MINERU_DONE_STATES
            }
            if not expected_ids <= (terminal_ids | local_terminal_ids):
                next_active.append(batch)
        active = next_active
        if active:
            remaining = deadline - time.time()
            if remaining > 0:
                await _sleep(min(config.poll_interval_seconds, remaining))

    for batch in active:
        for item in batch["items"]:
            paper = paper_by_data_id[item["data_id"]]
            if paper.mineru.get("state") not in MINERU_DONE_STATES:
                previous = paper.mineru.get("state")
                kb.set_mineru_state(
                    paper,
                    {
                        "state": "skipped",
                        "reason": "MinerU timeout; using Sciverse evidence",
                        "mineru_last_state": previous,
                    },
                )

    states: dict[str, int] = {}
    for paper in kb.papers:
        state = str(paper.mineru.get("state") or "not_submitted")
        states[state] = states.get(state, 0) + 1
    return {"enabled": True, "submitted": len(work_items), **states}


async def _sleep(seconds: float) -> None:
    import asyncio

    await asyncio.sleep(seconds)
