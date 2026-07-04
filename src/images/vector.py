from __future__ import annotations

import html
import re
import textwrap
from pathlib import Path

from ..state.kb import LiteratureKB
from .generator import GeneratedImage
from .planner import FigurePlan


def render_svg_figure(plan: FigurePlan, kb: LiteratureKB, output_dir: Path) -> GeneratedImage:
    output_dir.mkdir(parents=True, exist_ok=True)
    path = output_dir / plan.filename
    if plan.figure_type == "research_agenda":
        svg = _research_agenda_svg(plan, kb)
    elif plan.figure_type == "comparison_matrix":
        svg = _comparison_matrix_svg(plan, kb)
    else:
        svg = _taxonomy_svg(plan, kb)
    path.write_text(svg, encoding="utf-8")
    return GeneratedImage(
        figure_id=plan.figure_id,
        title=plan.title,
        caption=plan.caption,
        prompt=plan.prompt,
        path=str(path),
        model="local-svg",
        size="1536x1024",
        quality="vector",
        render_mode="svg",
        figure_type=plan.figure_type,
        target_heading=plan.target_heading,
        source_evidence_ids=plan.source_evidence_ids,
    )


def _taxonomy_svg(plan: FigurePlan, kb: LiteratureKB) -> str:
    evidence_text = _plan_text(plan, kb)
    groups = [
        ("Method Families", _keyword_items(evidence_text, _METHOD_TERMS, fallback=["Core methods", "Hybrid methods", "Evaluation methods", "Applications"])),
        ("Evidence Themes", _keyword_items(evidence_text, _THEME_TERMS, fallback=["Data", "Modeling", "Evaluation", "Deployment"])),
        ("Application Contexts", _keyword_items(evidence_text, _DOMAIN_TERMS, fallback=["Research", "Practice", "Systems", "Users"])),
    ]
    cards = []
    x_positions = [80, 560, 1040]
    for col, (title, items) in enumerate(groups):
        x = x_positions[col]
        cards.append(_rect(x, 160, 360, 560, "#f8fbff", "#9bb7e0"))
        cards.append(_text(title, x + 180, 215, 26, "#173b68", anchor="middle", weight="700"))
        for row, item in enumerate(items):
            y = 270 + row * 90
            cards.append(_rect(x + 38, y, 284, 56, "#ffffff", "#d1dce8", radius=16))
            cards.append(_text(item, x + 180, y + 36, 21, "#172033", anchor="middle", weight="600"))
    footer = _source_footer(plan.source_evidence_ids)
    return _svg_shell(plan.title, "\n".join(cards) + footer)


def _comparison_matrix_svg(plan: FigurePlan, kb: LiteratureKB) -> str:
    rows = _evidence_rows(plan, kb)[:6]
    headers = ["Evidence", "Method family", "Representation", "Primary use", "Risk / limitation"]
    col_x = [70, 250, 520, 800, 1090]
    col_w = [150, 230, 230, 250, 330]
    parts = [_text(plan.title, 768, 70, 30, "#102a4c", anchor="middle", weight="800")]
    y = 120
    for i, header in enumerate(headers):
        parts.append(_rect(col_x[i], y, col_w[i], 54, "#173b68", "#173b68", radius=10))
        parts.append(_text(header, col_x[i] + col_w[i] / 2, y + 34, 17, "#ffffff", anchor="middle", weight="700"))
    for row_index, row in enumerate(rows):
        y = 178 + row_index * 112
        fill = "#ffffff" if row_index % 2 == 0 else "#f6f9fc"
        cells = [
            row["evidence_id"],
            row["family"],
            row["representation"],
            row["use"],
            row["risk"],
        ]
        for i, cell in enumerate(cells):
            parts.append(_rect(col_x[i], y, col_w[i], 100, fill, "#d7e0ea", radius=8))
            parts.extend(_wrapped_text(cell, col_x[i] + 14, y + 30, col_w[i] - 28, 16, "#172033"))
    parts.append(_source_footer(plan.source_evidence_ids, y=910))
    return _svg_shell(plan.title, "\n".join(parts))


def _research_agenda_svg(plan: FigurePlan, kb: LiteratureKB) -> str:
    items = _agenda_items(plan.prompt or _plan_text(plan, kb))[:6]
    colors = ["#e8f3ff", "#edf8f0", "#fff6df", "#f7eefb", "#fff0f0", "#edf5f7"]
    parts = [_text(plan.title, 768, 76, 32, "#102a4c", anchor="middle", weight="800")]
    for idx, item in enumerate(items):
        row = idx // 3
        col = idx % 3
        x = 120 + col * 460
        y = 170 + row * 260
        parts.append(_rect(x, y, 360, 180, colors[idx], "#d9e2ec", radius=24))
        parts.append(_text(f"{idx + 1}", x + 44, y + 58, 36, "#173b68", anchor="middle", weight="800"))
        parts.extend(_wrapped_text(item, x + 90, y + 62, 220, 24, "#16233a", weight="700"))
        parts.extend(_wrapped_text(_agenda_hint(item), x + 42, y + 120, 280, 15, "#46566b"))
    parts.append(_source_footer(plan.source_evidence_ids, y=860))
    return _svg_shell(plan.title, "\n".join(parts))


def _evidence_rows(plan: FigurePlan, kb: LiteratureKB) -> list[dict[str, str]]:
    rows = []
    for evidence_id in plan.source_evidence_ids:
        evidence = kb.get_evidence(evidence_id)
        text = f"{evidence.title} {evidence.text}" if evidence else evidence_id
        rows.append(
            {
                "evidence_id": evidence_id,
                "family": _best_term(text, _METHOD_TERMS, "Method"),
                "representation": _best_term(text, _THEME_TERMS, "Evidence theme"),
                "use": _best_term(text, _USE_TERMS, "Primary claim"),
                "risk": _best_term(text, _RISK_TERMS, "Open limitation"),
            }
        )
    return rows


def _agenda_hint(item: str) -> str:
    return f"Research direction identified from cited section evidence: {item.lower()}."


_METHOD_TERMS = [
    "model-based learning",
    "generative modeling",
    "retrieval augmentation",
    "contrastive learning",
    "diffusion models",
    "transformers",
    "simulation",
    "benchmarking",
    "planning",
    "control",
    "optimization",
    "representation learning",
]

_THEME_TERMS = [
    "data efficiency",
    "generalization",
    "interpretability",
    "physical grounding",
    "safety",
    "evaluation",
    "scalability",
    "multimodality",
    "uncertainty",
    "causal reasoning",
    "long-horizon reasoning",
    "standardization",
]

_DOMAIN_TERMS = [
    "robotics",
    "autonomous driving",
    "healthcare",
    "web agents",
    "science",
    "education",
    "games",
    "language agents",
    "edge systems",
    "multi-agent systems",
    "decision support",
    "human interaction",
]

_USE_TERMS = [
    "prediction",
    "planning",
    "generation",
    "classification",
    "reasoning",
    "control",
    "forecasting",
    "synthesis",
    "analysis",
    "evaluation",
]

_RISK_TERMS = [
    "hallucination",
    "bias",
    "robustness",
    "safety",
    "scalability",
    "data quality",
    "evaluation gap",
    "reproducibility",
    "cost",
    "latency",
    "uncertainty",
]


def _plan_text(plan: FigurePlan, kb: LiteratureKB) -> str:
    chunks = [plan.prompt, plan.title, plan.caption]
    for evidence_id in plan.source_evidence_ids:
        evidence = kb.get_evidence(evidence_id)
        if evidence:
            chunks.extend([evidence.title, evidence.text])
    return " ".join(chunks)


def _keyword_items(text: str, vocabulary: list[str], *, fallback: list[str]) -> list[str]:
    lower = text.lower()
    scored = []
    for term in vocabulary:
        score = lower.count(term.lower())
        if score:
            scored.append((score, term.title()))
    items = [term for _, term in sorted(scored, key=lambda item: (-item[0], item[1]))]
    for item in fallback:
        if len(items) >= 4:
            break
        if item not in items:
            items.append(item)
    return items[:4]


def _best_term(text: str, vocabulary: list[str], fallback: str) -> str:
    items = _keyword_items(text, vocabulary, fallback=[fallback])
    return items[0] if items else fallback


def _agenda_items(text: str) -> list[str]:
    lower = text.lower()
    candidates: list[str] = []
    for term in _THEME_TERMS + _RISK_TERMS + _USE_TERMS:
        if term.lower() in lower:
            candidates.append(term.title())
    if len(candidates) < 6:
        phrases = re.findall(r"\b(?:future|open|need|challenge|direction|standard|safety|evaluation)\w*\b[^.]{0,60}", text, flags=re.I)
        for phrase in phrases:
            cleaned = re.sub(r"\s+", " ", phrase).strip(" ,;:-")
            if 8 <= len(cleaned) <= 48:
                candidates.append(cleaned[0].upper() + cleaned[1:])
    fallback = ["Evaluation", "Robustness", "Scalability", "Reproducibility", "Safety", "Deployment"]
    unique: list[str] = []
    for item in candidates + fallback:
        normalized = item.lower()
        if normalized not in {seen.lower() for seen in unique}:
            unique.append(item)
        if len(unique) >= 6:
            break
    return unique


def _svg_shell(title: str, body: str) -> str:
    return f"""<svg xmlns="http://www.w3.org/2000/svg" width="1536" height="1024" viewBox="0 0 1536 1024" role="img" aria-label="{html.escape(title)}">
<rect width="1536" height="1024" fill="#ffffff"/>
{body}
</svg>
"""


def _rect(x: float, y: float, w: float, h: float, fill: str, stroke: str, radius: int = 18) -> str:
    return f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="{radius}" fill="{fill}" stroke="{stroke}" stroke-width="2"/>'


def _text(text: str, x: float, y: float, size: int, color: str, anchor: str = "start", weight: str = "500") -> str:
    return f'<text x="{x}" y="{y}" font-family="Inter, Arial, sans-serif" font-size="{size}" font-weight="{weight}" text-anchor="{anchor}" fill="{color}">{html.escape(text)}</text>'


def _wrapped_text(text: str, x: float, y: float, width: float, size: int, color: str, weight: str = "500") -> list[str]:
    max_chars = max(8, int(width / (size * 0.55)))
    lines = textwrap.wrap(re.sub(r"\s+", " ", text), width=max_chars)[:4]
    return [_text(line, x, y + idx * (size + 7), size, color, weight=weight) for idx, line in enumerate(lines)]


def _source_footer(evidence_ids: list[str], y: int = 820) -> str:
    source_text = "Sources: " + ", ".join(evidence_ids[:8])
    return _text(source_text, 768, y, 18, "#536579", anchor="middle", weight="600")
