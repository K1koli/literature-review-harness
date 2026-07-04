from __future__ import annotations

from dataclasses import dataclass, field

from .manager import SkillMetadata


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
        selected: list[str] = []
        for meta in candidates:
            meta_roles = {_normalize(role) for role in meta.roles}
            if meta.enabled and (meta_roles & wanted):
                selected.append(meta.name)
        return SkillRouteDecision(
            phase=phase,
            selected_names=selected,
            roles=roles,
            reason=(
                f"selected skills whose metadata roles match phase '{phase}' for topic '{topic}'; "
                "full instructions are loaded only after routing"
            ),
            available_names=available,
        )


def _normalize(value: str) -> str:
    return value.lower().replace("-", "_").replace(" ", "_")
