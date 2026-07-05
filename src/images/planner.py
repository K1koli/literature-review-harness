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

    limit = min(max(max_figures, 0), 4)
    if limit == 0:
        return []

    sections = parse_markdown_sections(survey_markdown)
    candidates: list[FigurePlan] = []

    intro = _find_section(sections, ["introduction", "background"])
    if intro:
        candidates.append(_conceptual_overview_plan(topic, intro, kb, skill_guidance))

    methods = _find_section(sections, ["taxonomy", "method", "architecture", "approach", "paradigm"])
    if methods:
        candidates.append(_taxonomy_plan(topic, methods, kb, skill_guidance))

    applications = _find_section(sections, ["application", "domain", "robot", "control", "game"])
    if applications:
        candidates.append(_application_plan(topic, applications, kb, skill_guidance))

    comparative = _find_section(sections, ["comparative", "comparison", "analysis", "evaluation", "benchmark"])
    if comparative:
        candidates.append(_comparison_plan(topic, comparative, kb))

    future = _find_section(sections, ["future", "open challenge", "challenge", "agenda"])
    if future:
        candidates.append(_agenda_plan(topic, future, kb, skill_guidance))

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
    return FigurePlan(
        figure_id="F000",
        title=f"{topic} Literature Taxonomy Map",
        caption=f"Visual map of the review's literature organization introduced in '{section.title}'.",
        target_heading=section.title,
        figure_type="literature_taxonomy_map",
        render_mode="image",
        source_evidence_ids=evidence_ids,
        filename="figure_000_literature_taxonomy_map.png",
        prompt=_image_prompt(
            topic=topic,
            section=section,
            evidence_count=len(evidence_ids),
            diagram_goal=(
                "Create the main survey figure: a visually polished map that groups the reviewed literature "
                "into coherent families, subfamilies, application areas, and open-problem branches."
            ),
            visual_metaphor=(
                "Use an elegant technical tree, radial map, metro map, or layered ecosystem diagram. "
                "Small abstract icons are encouraged when they clarify categories."
            ),
            logic_requirements=[
                "The hierarchy must be clear: root topic -> major literature families -> representative subtopics.",
                "Use arrows or branches only where they show a real progression or dependency.",
                "Make the figure useful as a reader's navigation map for the whole survey.",
            ],
            skill_guidance=skill_guidance,
        ),
    )


def _taxonomy_plan(topic: str, section: SurveySection, kb: LiteratureKB, skill_guidance: str) -> FigurePlan:
    evidence_ids = _source_ids(section)
    return FigurePlan(
        figure_id="F000",
        title=f"{topic} Method Taxonomy",
        caption=f"Evidence-grounded taxonomy of method families discussed in '{section.title}'.",
        target_heading=section.title,
        figure_type="method_taxonomy",
        render_mode="image",
        source_evidence_ids=evidence_ids,
        filename="figure_000_method_taxonomy.png",
        prompt=_image_prompt(
            topic=topic,
            section=section,
            evidence_count=len(evidence_ids),
            diagram_goal="Create a method-family taxonomy figure for this survey section.",
            visual_metaphor="Use grouped panels, nested cards, or a clean branching tree with tasteful academic icons.",
            logic_requirements=[
                "Separate method families visually and show how they differ by representation, objective, or usage.",
                "Use consistent visual grammar: one shape type for families, another for subfamilies.",
                "Do not make a generic decorative poster; the grouping logic must be readable.",
            ],
            skill_guidance=skill_guidance,
        ),
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


def _application_plan(topic: str, section: SurveySection, kb: LiteratureKB, skill_guidance: str) -> FigurePlan:
    evidence_ids = _source_ids(section)
    return FigurePlan(
        figure_id="F000",
        title=f"{topic} Application Map",
        caption=f"Application contexts and deployment settings discussed in '{section.title}'.",
        target_heading=section.title,
        figure_type="application_map",
        render_mode="image",
        source_evidence_ids=evidence_ids,
        filename="figure_000_application_map.png",
        prompt=_image_prompt(
            topic=topic,
            section=section,
            evidence_count=len(evidence_ids),
            diagram_goal="Create an application landscape figure for this survey section.",
            visual_metaphor="Use a hub-and-spoke map, layered deployment diagram, or domain landscape with small abstract icons.",
            logic_requirements=[
                "Group application domains by role or deployment setting.",
                "Show how methods connect to applications without implying unsupported quantitative rankings.",
                "If arrows are used, their direction must indicate data flow, deployment flow, or conceptual dependency.",
            ],
            skill_guidance=skill_guidance,
        ),
    )


def _agenda_plan(topic: str, section: SurveySection, kb: LiteratureKB, skill_guidance: str) -> FigurePlan:
    evidence_ids = _source_ids(section)
    return FigurePlan(
        figure_id="F000",
        title=f"{topic} Research Agenda",
        caption=f"Open challenges and research directions extracted from '{section.title}'.",
        target_heading=section.title,
        figure_type="research_agenda",
        render_mode="image",
        source_evidence_ids=evidence_ids,
        filename="figure_000_research_agenda.png",
        prompt=_image_prompt(
            topic=topic,
            section=section,
            evidence_count=len(evidence_ids),
            diagram_goal="Create a future-research roadmap figure for this survey section.",
            visual_metaphor="Use a roadmap, layered funnel, or branching challenge-to-opportunity diagram.",
            logic_requirements=[
                "Show limitations leading to research opportunities in a clear left-to-right or bottom-to-top flow.",
                "Use arrows only to express problem-to-direction logic.",
                "Avoid unsupported predictions, numeric forecasts, or hype language.",
            ],
            skill_guidance=skill_guidance,
        ),
    )


def _image_prompt(
    *,
    topic: str,
    section: SurveySection,
    evidence_count: int,
    diagram_goal: str,
    visual_metaphor: str,
    logic_requirements: list[str],
    skill_guidance: str,
) -> str:
    cues = ", ".join(_content_cues(section))
    logic = "\n".join(f"- {item}" for item in logic_requirements)
    return f"""
Create a publication-quality academic diagram for a literature survey.

Topic: {topic}
Target section: {section.title}
Goal: {diagram_goal}
Evidence-backed content cues: {cues}
Source support: {evidence_count} cited evidence records. Source details stay in the caption, not inside the image.

Visual direction:
- {visual_metaphor}
- Render as a clean raster image with the precision of a vector infographic.
- Use a restrained but attractive palette, crisp lines, generous whitespace, and balanced composition.
- Use at most 10 short labels, each under 4 words.
- Prefer icons, shapes, arrows, grouping, and hierarchy over dense text.

Logical requirements:
{logic}

Content constraints:
- Use only abstract academic infographic elements: blocks, arrows, branches, clusters, icons, timelines, and labels.
- Keep all factual support in the survey text and caption; the image should communicate structure, not exact claims.
- Avoid real-world scenes, identifiable entities, brands, screenshots, source code, equations, citation strings, author names, paper titles, DOI strings, and benchmark numbers.
- The result must look like a figure from a serious ML/AI survey paper, not a marketing poster.

Figure-skill guidance:
{_clean(_plain_skill_guidance(skill_guidance), 420)}
""".strip()


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
