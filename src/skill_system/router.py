from __future__ import annotations

from dataclasses import dataclass, field

from .manager import SkillMetadata


PHASE_MAX_SKILLS: dict[str, int] = {
    "literature_review": 4,
    "framing": 2,
    "outline": 3,
    "section_write": 3,
    "citation_check": 2,
    "polish": 2,
    "write": 3,
    "verify": 2,
    "figure": 2,
    "revise": 2,
    "export": 2,
}

PHASE_PREFERRED_SKILLS: dict[str, list[str]] = {
    "literature_review": ["research-framing", "survey-writing", "citation-grounding", "agent-literature-review"],
    "framing": ["research-framing", "craft-of-research", "agent-literature-review"],
    "outline": ["survey-writing", "research-framing", "agent-survey-generation", "agent-literature-review"],
    "section_write": ["survey-writing", "citation-grounding", "agent-survey-generation", "agent-related-work-writing"],
    "citation_check": ["citation-grounding", "agent-citation-management", "agent-literature-review"],
    "polish": ["academic-polishing", "agent-paper-revision", "agent-self-review", "nature-polishing"],
    "write": ["survey-writing", "agent-survey-generation", "agent-related-work-writing"],
    "verify": ["citation-grounding", "agent-literature-review"],
    "figure": ["agent-figure-generation"],
    "export": ["latex-arxiv-export", "arxiv-paper-writer"],
}


@dataclass(frozen=True)
class SkillRouteDecision:
    phase: str
    selected_names: list[str]
    roles: list[str] = field(default_factory=list)
    reason: str = ""
    available_names: list[str] = field(default_factory=list)


class SkillRouter:
    """Metadata-only skill router.

    Routing happens before full skill content is loaded, which is the key
    progressive-disclosure boundary.
    """

    def route(
        self,
        *,
        phase: str,
        topic: str,
        candidates: list[SkillMetadata],
        roles: list[str],
        explicit_names: list[str] | None = None,
    ) -> SkillRouteDecision:
        available = [meta.name for meta in candidates]
        if explicit_names:
            selected = [name for name in explicit_names if name in available]
            missing = [name for name in explicit_names if name not in available]
            reason = "explicit skill override requested"
            if missing:
                reason += "; missing skills ignored: " + ", ".join(missing)
            return SkillRouteDecision(phase=phase, selected_names=selected, roles=roles, reason=reason, available_names=available)

        wanted = {_normalize(role) for role in roles}
        matching = []
        for meta in candidates:
            meta_roles = {_normalize(role) for role in meta.roles}
            overlap = meta_roles & wanted
            if meta.enabled and overlap:
                matching.append(meta)
        preferred = PHASE_PREFERRED_SKILLS.get(phase, [])
        matching = sorted(matching, key=lambda meta: _priority(meta, wanted, preferred))
        max_selected = PHASE_MAX_SKILLS.get(phase, len(matching))
        selected = [meta.name for meta in matching[:max_selected]]
        return SkillRouteDecision(
            phase=phase,
            selected_names=selected,
            roles=roles,
            reason=(
                f"selected skills whose metadata roles match phase '{phase}' for topic '{topic}'; "
                f"full instructions are loaded only after routing; capped at {max_selected} skill(s)"
            ),
            available_names=available,
        )


def _normalize(value: str) -> str:
    return value.lower().replace("-", "_").replace(" ", "_")


def _priority(meta: SkillMetadata, wanted: set[str], preferred: list[str]) -> tuple[int, int, int, int, str]:
    roles = {_normalize(role) for role in meta.roles}
    overlap_count = len(roles & wanted)
    preferred_rank = preferred.index(meta.name) if meta.name in preferred else 999
    source_rank = 0 if meta.source == "builtin" else 1
    role_specificity = len(roles)
    return (preferred_rank, source_rank, -overlap_count, role_specificity, meta.name)
