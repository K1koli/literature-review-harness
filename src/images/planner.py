from __future__ import annotations

import re
from dataclasses import asdict, dataclass
from typing import Any

from ..state.kb import LiteratureKB
from ..validation.citations import EVIDENCE_ID_RE


HEADING_RE = re.compile(r"^(#{1,6})\s+(.+?)\s*$")


@dataclass
class SurveySection:
    level: int
    title: str
    body: str
    start_line: int
    evidence_ids: list[str]


@dataclass
class FigurePlan:
    figure_id: str
    title: str
    caption: str
    target_heading: str
    figure_type: str
    render_mode: str
    source_evidence_ids: list[str]
    filename: str
    prompt: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def plan_survey_figures(
    *,
    topic: str,
    survey_markdown: str,
    kb: LiteratureKB,
    max_figures: int,
    skill_guidance: str = "",
) -> list[FigurePlan]:
    """Plan a small, section-aware figure set.

    The planner is intentionally conservative: it only selects sections that
    already cite evidence ids, caps the total number of figures, and prefers
    deterministic SVG for text-heavy tables or matrices.
    """

    limit = min(max(max_figures, 0), 3)
    if limit == 0:
        return []

    sections = parse_markdown_sections(survey_markdown)
    candidates: list[FigurePlan] = []

    intro = _find_section(sections, ["introduction", "background"])
    if intro:
        candidates.append(_conceptual_overview_plan(topic, intro, kb, skill_guidance))

    methods = _find_section(sections, ["key approaches", "methods", "approaches"])
    if methods:
        candidates.append(_taxonomy_plan(topic, methods, kb))

    comparative = _find_section(sections, ["comparative", "comparison", "analysis"])
    if comparative:
        candidates.append(_comparison_plan(topic, comparative, kb))

    future = _find_section(sections, ["future", "open challenge", "challenge", "agenda"])
    if future:
        candidates.append(_agenda_plan(topic, future, kb))

    deduped: list[FigurePlan] = []
    seen_headings: set[str] = set()
    for candidate in candidates:
        if not candidate.source_evidence_ids:
            continue
        key = candidate.target_heading.lower()
        if key in seen_headings:
            continue
        seen_headings.add(key)
        deduped.append(candidate)

    selected = deduped[:limit]
    for index, plan in enumerate(selected, start=1):
        plan.figure_id = f"F{index:03d}"
        stem = plan.figure_type.replace("_", "-")
        suffix = "png" if plan.render_mode == "image" else "svg"
        plan.filename = f"figure_{index:03d}_{stem}.{suffix}"
    return selected


def parse_markdown_sections(markdown: str) -> list[SurveySection]:
    lines = markdown.splitlines()
    headings: list[tuple[int, int, str]] = []
    for index, line in enumerate(lines):
        match = HEADING_RE.match(line)
        if match:
            headings.append((index, len(match.group(1)), match.group(2).strip()))
    sections: list[SurveySection] = []
    for pos, (start, level, title) in enumerate(headings):
        end = len(lines)
        for next_start, next_level, _ in headings[pos + 1 :]:
            if next_level <= level:
                end = next_start
                break
        body = "\n".join(lines[start + 1 : end]).strip()
        evidence_ids = sorted(set(EVIDENCE_ID_RE.findall(body)))
        sections.append(SurveySection(level=level, title=title, body=body, start_line=start, evidence_ids=evidence_ids))
    return sections


def _find_section(sections: list[SurveySection], keywords: list[str]) -> SurveySection | None:
    for section in sections:
        if section.level != 2 or not section.evidence_ids:
            continue
        title = section.title.lower()
        if any(keyword in title for keyword in keywords):
            return section
    return None


def _source_ids(section: SurveySection, *, max_items: int = 8) -> list[str]:
    return section.evidence_ids[:max_items]


def _paper_context(kb: LiteratureKB, evidence_ids: list[str]) -> str:
    lines = []
    for evidence_id in evidence_ids:
        evidence = kb.get_evidence(evidence_id)
        if evidence is None:
            continue
        year = evidence.year or "n.d."
        lines.append(f"- {evidence_id}: {year}, {evidence.title}")
    return "\n".join(lines) or "- No source metadata available"


def _content_cues(section: SurveySection, *, max_items: int = 8) -> list[str]:
    text = re.sub(r"\[[A-Z]\d{3}-E\d{2}\]", " ", section.body.lower())
    vocabulary = [
        "latent dynamics",
        "prediction",
        "planning",
        "simulation",
        "generative model",
        "reinforcement learning",
        "video generation",
        "robotics",
        "autonomous agents",
        "evaluation",
        "representation learning",
        "world model",
    ]
    cues = [term for term in vocabulary if term in text]
    if not cues:
        cues = ["observations", "latent model", "future states", "planning"]
    return cues[:max_items]


def _clean(value: str, max_chars: int = 2200) -> str:
    return re.sub(r"\s+", " ", value or "").strip()[:max_chars]


def _conceptual_overview_plan(topic: str, section: SurveySection, kb: LiteratureKB, skill_guidance: str) -> FigurePlan:
    evidence_ids = _source_ids(section)
    cues = ", ".join(_content_cues(section))
    prompt = f"""
Create a polished academic survey figure for {topic}.

Target section: {section.title}
Content cues distilled from the evidence-backed section:
{cues}

Source support: {len(evidence_ids)} cited evidence records. Source details remain in the caption, not in the image prompt.

Design constraints:
- Use a clean conference-paper visual style, like a vector diagram rendered as a raster image.
- Show the review's organizing logic with blocks, arrows, layers, or clusters.
- Prefer a taxonomy, lifecycle, or relationship diagram over decorative illustration.
- Use at most 8 short labels, each under 4 words.
- Prefer icons, shapes, arrows, and spatial grouping over written text.
- Avoid people, faces, vehicles, medical scenes, brands, logos, screenshots, code, equations, citation ids, author names, and paper titles.
- Do not render exact years, paper titles, author names, citation ids, DOI strings, equations, or numeric benchmark values inside the image.
- Factual claims and source attribution remain in the caption and survey text, not inside the image.
- Leave enough whitespace for the figure to be readable at article width.

Figure-skill guidance:
{_clean(_plain_skill_guidance(skill_guidance), 420)}
""".strip()
    return FigurePlan(
        figure_id="F000",
        title=f"{topic} Conceptual Overview",
        caption=f"Conceptual overview for the section '{section.title}'.",
        target_heading=section.title,
        figure_type="conceptual_overview",
        render_mode="image",
        source_evidence_ids=evidence_ids,
        filename="figure_000_conceptual_overview.png",
        prompt=prompt,
    )


def _taxonomy_plan(topic: str, section: SurveySection, kb: LiteratureKB) -> FigurePlan:
    evidence_ids = _source_ids(section)
    return FigurePlan(
        figure_id="F000",
        title=f"{topic} Method Taxonomy",
        caption=f"Evidence-grounded taxonomy of method families discussed in '{section.title}'.",
        target_heading=section.title,
        figure_type="method_taxonomy",
        render_mode="svg",
        source_evidence_ids=evidence_ids,
        filename="figure_000_method_taxonomy.svg",
        prompt=_clean(section.body, 2200),
    )


def _comparison_plan(topic: str, section: SurveySection, kb: LiteratureKB) -> FigurePlan:
    evidence_ids = _source_ids(section)
    return FigurePlan(
        figure_id="F000",
        title=f"{topic} Comparison Matrix",
        caption=f"Qualitative comparison matrix derived from cited evidence in '{section.title}'.",
        target_heading=section.title,
        figure_type="comparison_matrix",
        render_mode="svg",
        source_evidence_ids=evidence_ids,
        filename="figure_000_comparison_matrix.svg",
        prompt=_clean(section.body, 2200),
    )


def _agenda_plan(topic: str, section: SurveySection, kb: LiteratureKB) -> FigurePlan:
    evidence_ids = _source_ids(section)
    return FigurePlan(
        figure_id="F000",
        title=f"{topic} Research Agenda",
        caption=f"Open challenges and research directions extracted from '{section.title}'.",
        target_heading=section.title,
        figure_type="research_agenda",
        render_mode="svg",
        source_evidence_ids=evidence_ids,
        filename="figure_000_research_agenda.svg",
        prompt=_clean(section.body, 2200),
    )


def _plain_skill_guidance(text: str) -> str:
    if not text:
        return ""
    text = re.sub(r"<!--.*?-->", " ", text, flags=re.DOTALL)
    text = re.sub(r"```.*?```", " ", text, flags=re.DOTALL)
    text = re.sub(r"`[^`]+`", " ", text)
    text = re.sub(r"/\S+", " ", text)
    lines = []
    for line in text.splitlines():
        stripped = line.strip(" #-")
        if not stripped:
            continue
        if any(token in stripped.lower() for token in ["script", "bash", "python", "path", "input"]):
            continue
        lines.append(stripped)
        if len(lines) >= 4:
            break
    return " ".join(lines)
