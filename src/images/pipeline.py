from __future__ import annotations

import asyncio
import json
import os
import re
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Any

from ..state.kb import LiteratureKB
from ..utils.config import Config
from .generator import GeneratedImage, OpenAIImageGenerator
from .planner import FigurePlan, plan_survey_figures
from .vector import render_svg_figure


@dataclass
class ImageGenerationResult:
    enabled: bool
    generated: list[GeneratedImage] = field(default_factory=list)
    skipped_reason: str | None = None
    errors: list[dict[str, str]] = field(default_factory=list)
    manifest_path: str | None = None
    figure_plan_path: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "enabled": self.enabled,
            "generated": [item.to_dict() for item in self.generated],
            "skipped_reason": self.skipped_reason,
            "errors": self.errors,
            "manifest_path": self.manifest_path,
            "figure_plan_path": self.figure_plan_path,
        }


def insert_figures_into_sections(survey_path: Path, figures: list[GeneratedImage]) -> None:
    if not figures:
        return

    survey_text = survey_path.read_text(encoding="utf-8")
    survey_text = _strip_legacy_illustrations(survey_text)
    lines = survey_text.splitlines()
    insertions: list[tuple[int, str]] = []

    for figure in figures:
        target_index = _find_heading_insert_index(lines, figure.target_heading)
        insertions.append((target_index, _figure_markdown_block(survey_path, figure)))

    for index, block in sorted(insertions, key=lambda item: item[0], reverse=True):
        lines[index:index] = block.splitlines()

    survey_path.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")


async def generate_survey_images(
    *,
    config: Config,
    topic: str,
    survey_markdown: str,
    kb: LiteratureKB,
    output_dir: Path,
    survey_path: Path | None = None,
    figures_dir: Path | None = None,
    figure_plan_path: Path | None = None,
    figure_plans: list[FigurePlan] | None = None,
    skill_guidance: str = "",
) -> ImageGenerationResult:
    if not config.image_generation_enabled:
        return ImageGenerationResult(enabled=False, skipped_reason="disabled")

    image_dir = figures_dir or (output_dir / "figures")
    manifest_path = image_dir / "figure_manifest.json"
    plan_path = figure_plan_path or (output_dir / "figure_plan.json")
    result = ImageGenerationResult(enabled=True, manifest_path=str(manifest_path), figure_plan_path=str(plan_path))
    _clean_previous_figures(image_dir)
    if figure_plans is not None:
        plans = figure_plans
    else:
        plans = plan_survey_figures(
            topic=topic,
            survey_markdown=survey_markdown,
            kb=kb,
            max_figures=config.image_generation_count,
            skill_guidance=skill_guidance,
        )
    plan_path.parent.mkdir(parents=True, exist_ok=True)
    plan_path.write_text(json.dumps([plan.to_dict() for plan in plans], ensure_ascii=False, indent=2), encoding="utf-8")

    generator = None
    if config.openai_image_api_key:
        generator = OpenAIImageGenerator(
            api_key=config.openai_image_api_key,
            base_url=config.openai_image_base_url,
            endpoint_path=config.openai_image_endpoint_path,
            model=config.openai_image_model,
            models=config.openai_image_models,
            size=config.image_generation_size,
            quality=config.image_generation_quality,
            timeout_seconds=config.image_generation_timeout,
        )

    for spec in plans:
        try:
            if spec.render_mode == "svg":
                generated = render_svg_figure(spec, kb, image_dir)
            else:
                if generator is None:
                    raise ValueError("OpenAI image API key is required for raster image figures")
                try:
                    generated = await asyncio.wait_for(
                        generator.generate(spec, image_dir),
                        timeout=max(config.image_generation_timeout, 1),
                    )
                except Exception as exc:
                    if not _is_policy_retryable(exc):
                        raise
                    retry_spec = _safe_image_retry_spec(spec)
                    generated = await asyncio.wait_for(
                        generator.generate(retry_spec, image_dir),
                        timeout=max(config.image_generation_timeout, 1),
                    )
            result.generated.append(generated)
        except Exception as exc:
            result.errors.append({"figure_id": spec.figure_id, "error": str(exc)})
            if spec.render_mode != "svg":
                try:
                    fallback = render_svg_figure(_svg_fallback_spec(spec), kb, image_dir)
                    result.generated.append(fallback)
                    result.errors.append(
                        {
                            "figure_id": spec.figure_id,
                            "error": "raster image generation failed; used local SVG fallback",
                        }
                    )
                except Exception as fallback_exc:
                    result.errors.append({"figure_id": spec.figure_id, "error": f"svg fallback failed: {fallback_exc}"})

    image_dir.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(json.dumps(result.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8")

    if survey_path is not None and result.generated:
        insert_figures_into_sections(survey_path, result.generated)

    return result


def _clean_previous_figures(image_dir: Path) -> None:
    if not image_dir.exists():
        return
    for path in image_dir.glob("figure_*"):
        if path.is_file() and path.suffix.lower() in {".png", ".jpg", ".jpeg", ".webp", ".svg"}:
            path.unlink()


def _strip_legacy_illustrations(text: str) -> str:
    marker = "\n## Illustrations\n"
    if marker not in text:
        stripped = text
    else:
        stripped = text[: text.index(marker)].rstrip() + "\n"
    stripped = re.sub(r"\n?<figure id=\"F\d{3}\">.*?</figure>\n?", "\n", stripped, flags=re.DOTALL)
    return re.sub(r"\n{3,}", "\n\n", stripped).strip() + "\n"


def _find_heading_insert_index(lines: list[str], target_heading: str) -> int:
    if target_heading:
        wanted = target_heading.strip().lower()
        for index, line in enumerate(lines):
            stripped = line.strip()
            if stripped.startswith("##") and stripped.lstrip("#").strip().lower() == wanted:
                return index + 1
    for index, line in enumerate(lines):
        if line.strip().lower().startswith("## references"):
            return index
    return len(lines)


def _figure_markdown_block(survey_path: Path, figure: GeneratedImage) -> str:
    relative_path = os.path.relpath(Path(figure.path), survey_path.parent)
    return "\n".join(
        [
            "",
            f'<figure id="{figure.figure_id}">',
            "",
            f"![{figure.title}]({relative_path})",
            "",
            f"<figcaption><strong>{figure.figure_id}. {figure.title}.</strong> {figure.caption}</figcaption>",
            "",
            "</figure>",
            "",
            _figure_reference_sentence(figure),
            "",
        ]
    )


def _figure_reference_sentence(figure: GeneratedImage) -> str:
    return f"Figure {figure.figure_id} summarizes the visual organization of this section."


def _is_policy_retryable(exc: Exception) -> bool:
    message = str(exc).lower()
    return "content policy" in message or "http 403" in message or "forbidden" in message


def _safe_image_retry_spec(spec: FigurePlan) -> FigurePlan:
    prompt = f"""
Create a clean academic diagram for a literature survey.

Figure title: {spec.title}
Target section: {spec.target_heading}

Use a non-photorealistic vector-infographic look rendered as a raster image.
Show the section's organizing logic with simple geometric shapes, clusters, and arrows.

Constraints:
- Use at most six short generic labels.
- Use only abstract shapes, arrows, clusters, and simple academic icons.
- Keep factual claims in the article text; the image should show structure only.
- Keep the image calm, readable, and suitable for a conference paper.
- Leave generous whitespace and avoid dense text.
""".strip()
    return replace(spec, prompt=prompt)


def _svg_fallback_spec(spec: FigurePlan) -> FigurePlan:
    filename = re.sub(r"\.[A-Za-z0-9]+$", ".svg", spec.filename)
    if filename == spec.filename:
        filename = spec.filename + ".svg"
    return replace(
        spec,
        render_mode="svg",
        figure_type="method_taxonomy",
        filename=filename,
        prompt=spec.prompt or spec.caption or spec.title,
    )
