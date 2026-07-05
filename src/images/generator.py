from __future__ import annotations

import base64
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import httpx

from .planner import FigurePlan


@dataclass
class GeneratedImage:
    figure_id: str
    title: str
    caption: str
    prompt: str
    path: str
    model: str
    size: str
    quality: str
    render_mode: str = "image"
    figure_type: str = ""
    target_heading: str = ""
    source_evidence_ids: list[str] | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "figure_id": self.figure_id,
            "title": self.title,
            "caption": self.caption,
            "prompt": self.prompt,
            "path": self.path,
            "model": self.model,
            "size": self.size,
            "quality": self.quality,
            "render_mode": self.render_mode,
            "figure_type": self.figure_type,
            "target_heading": self.target_heading,
            "source_evidence_ids": self.source_evidence_ids or [],
        }


class OpenAIImageGenerator:
    """Small OpenAI Images API adapter.

    The harness keeps image generation as a post-processing step so image API
    failures do not block evidence verification or survey generation.
    """

    def __init__(
        self,
        *,
        api_key: str,
        base_url: str = "https://api.openai.com/v1",
        endpoint_path: str = "/images/generations",
        model: str = "gpt-image-1",
        models: list[str] | None = None,
        size: str = "1536x1024",
        quality: str = "low",
        timeout_seconds: int = 180,
    ) -> None:
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self.endpoint_path = endpoint_path
        self.model = model
        self.models = _dedupe(models or [model])
        self.size = size
        self.quality = quality
        self.timeout_seconds = timeout_seconds

    async def generate(self, spec: FigurePlan, output_dir: Path) -> GeneratedImage:
        if not self.api_key:
            raise ValueError("OpenAI image API key is required")

        output_dir.mkdir(parents=True, exist_ok=True)
        errors: list[str] = []
        for model in self.models:
            try:
                return await self._generate_with_model(spec, output_dir, model)
            except Exception as exc:
                errors.append(f"{model}: {exc}")
        raise ValueError("All image models failed: " + " | ".join(errors))

    async def _generate_with_model(self, spec: FigurePlan, output_dir: Path, model: str) -> GeneratedImage:
        image_path = output_dir / spec.filename
        payload: dict[str, Any] = {
            "model": model,
            "prompt": spec.prompt,
            "size": self.size,
            "n": 1,
        }
        if self.quality:
            payload["quality"] = self.quality

        async with httpx.AsyncClient(timeout=self.timeout_seconds) as client:
            response = await client.post(
                self._generation_url(),
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json",
                },
                json=payload,
            )
            try:
                response.raise_for_status()
            except httpx.HTTPStatusError as exc:
                body = response.text[:800].replace("\n", " ")
                raise ValueError(
                    f"Image API returned HTTP {response.status_code} for {response.url}: {body}"
                ) from exc
            data = response.json()

            item = self._first_image_item(data)
            if "b64_json" in item:
                image_path.write_bytes(base64.b64decode(item["b64_json"]))
            elif "url" in item:
                image_response = await client.get(item["url"])
                image_response.raise_for_status()
                image_path.write_bytes(image_response.content)
            else:
                raise ValueError("OpenAI image response did not include b64_json or url")

        return GeneratedImage(
            figure_id=spec.figure_id,
            title=spec.title,
            caption=spec.caption,
            prompt=spec.prompt,
            path=str(image_path),
            model=model,
            size=self.size,
            quality=self.quality,
            render_mode=getattr(spec, "render_mode", "image"),
            figure_type=getattr(spec, "figure_type", ""),
            target_heading=getattr(spec, "target_heading", ""),
            source_evidence_ids=list(getattr(spec, "source_evidence_ids", []) or []),
        )

    def _first_image_item(self, data: dict[str, Any]) -> dict[str, Any]:
        images = data.get("data")
        if not isinstance(images, list) or not images:
            raise ValueError("OpenAI image response did not include data[]")
        item = images[0]
        if not isinstance(item, dict):
            raise ValueError("OpenAI image response data[0] is not an object")
        return item

    def _generation_url(self) -> str:
        if self.base_url.endswith("/images/generations"):
            return self.base_url
        endpoint_path = self.endpoint_path or "/images/generations"
        if not endpoint_path.startswith("/"):
            endpoint_path = "/" + endpoint_path
        return f"{self.base_url}{endpoint_path}"


def _dedupe(values: list[str]) -> list[str]:
    result: list[str] = []
    for value in values:
        value = value.strip()
        if value and value not in result:
            result.append(value)
    return result or ["gpt-image-1"]
