from __future__ import annotations

from .manager import SkillManager
from .router import SkillRouter
from .trace import SkillTraceRecorder


class SkillContextInjector:
    """Pre-LLM hook that injects a small phase-routed skill context."""

    def __init__(
        self,
        manager: SkillManager,
        router: SkillRouter,
        trace: SkillTraceRecorder,
        *,
        phase: str = "literature_review",
        topic: str = "",
        roles: list[str] | None = None,
        enabled: bool = True,
    ):
        self.manager = manager
        self.router = router
        self.trace = trace
        self.phase = phase
        self.topic = topic
        self.roles = roles or ["research_framing", "survey_writing", "citation_grounding"]
        self.enabled = enabled
        self._context_text = ""
        self._loaded_names: list[str] = []
        self._loaded = False

    def __call__(self, messages: list[dict], tools: list[dict]) -> tuple[list[dict], list[dict]]:
        if not self.enabled:
            return messages, tools
        if not self._loaded:
            self._load_once()
        if not self._context_text:
            return messages, tools
        injected = [dict(message) for message in messages]
        skill_block = (
            "\n\n## Loaded Skill Protocols\n"
            "Use these as workflow guidance only; factual claims must still come from evidence ids in the KB.\n\n"
            + self._context_text
        )
        if injected and injected[0].get("role") == "system":
            injected[0]["content"] = str(injected[0].get("content", "")) + skill_block
        else:
            injected.insert(0, {"role": "system", "content": skill_block.strip()})
        self.trace.record(
            phase=self.phase,
            action="inject",
            skill_names=self._loaded_names,
            roles=self.roles,
            reason="injected loaded skill context into the LLM message list",
            injected_chars=len(self._context_text),
        )
        return injected, tools

    def _load_once(self) -> None:
        available = self.manager.list()
        self.trace.record(
            phase="discovery",
            action="discover",
            skill_names=[meta.name for meta in available],
            reason="loaded skill metadata index without loading full skill instructions",
            metadata={"count": len(available)},
        )
        decision = self.router.route(
            phase=self.phase,
            topic=self.topic,
            candidates=available,
            roles=self.roles,
        )
        self.trace.record(
            phase=self.phase,
            action="route",
            skill_names=decision.selected_names,
            roles=decision.roles,
            reason=decision.reason,
            metadata={"available_skills": decision.available_names},
        )
        context = self.manager.load_names(decision.selected_names, phase=self.phase)
        self._context_text = context.render()
        self._loaded_names = context.names
        self._loaded = True
        self.trace.record(
            phase=self.phase,
            action="load",
            skill_names=context.names,
            roles=self.roles,
            reason="loaded full skill instructions after metadata routing",
            injected_chars=len(self._context_text),
            resources=[f"{skill.name}:{resource}" for skill in context.active for resource in skill.loaded_resources],
        )

    def unload(self) -> None:
        before = self.manager.unload()
        self.trace.record(
            phase=self.phase,
            action="unload",
            skill_names=before or self._loaded_names,
            reason="cleared active skill context after run completion",
        )
