from __future__ import annotations

import json
from typing import Any

from .manager import PHASE_ROLES, SkillManager
from .router import SkillRouter
from .trace import SkillTraceRecorder


class SkillListIndexTool:
    name = "skills_list_index"
    description = "List available skill metadata only. Does not load full skill content."
    parameters = {"type": "object", "properties": {}}

    def __init__(self, manager: SkillManager, trace: SkillTraceRecorder):
        self.manager = manager
        self.trace = trace

    async def execute(self) -> str:
        items = [
            {
                "name": meta.name,
                "description": meta.description,
                "roles": meta.roles,
                "triggers": meta.triggers,
                "source": meta.source,
                "enabled": meta.enabled,
            }
            for meta in self.manager.list()
        ]
        self.trace.record(
            phase="manual",
            action="discover",
            skill_names=[item["name"] for item in items],
            reason="agent listed skill metadata without loading full skill instructions",
            metadata={"count": len(items)},
        )
        return json.dumps(items, ensure_ascii=False)


class SkillRouteForPhaseTool:
    name = "skills_route_for_phase"
    description = "Select skill names for a phase from metadata only, before loading full skill instructions."
    parameters = {
        "type": "object",
        "properties": {
            "phase": {"type": "string", "description": "Harness phase, e.g. literature_review, write, verify."},
            "topic": {"type": "string", "description": "Current review topic.", "default": ""},
            "roles": {"type": "array", "items": {"type": "string"}, "description": "Optional role override."},
        },
        "required": ["phase"],
    }

    def __init__(self, manager: SkillManager, router: SkillRouter, trace: SkillTraceRecorder):
        self.manager = manager
        self.router = router
        self.trace = trace

    async def execute(self, phase: str, topic: str = "", roles: list[str] | None = None) -> str:
        role_list = roles or PHASE_ROLES.get(phase, [])
        decision = self.router.route(phase=phase, topic=topic, candidates=self.manager.list(), roles=role_list)
        self.trace.record(
            phase=phase,
            action="route",
            skill_names=decision.selected_names,
            roles=decision.roles,
            reason=decision.reason,
            metadata={"available_skills": decision.available_names},
        )
        return json.dumps(
            {
                "phase": decision.phase,
                "selected_skills": decision.selected_names,
                "roles": decision.roles,
                "reason": decision.reason,
                "available_skills": decision.available_names,
            },
            ensure_ascii=False,
        )


class SkillLoadForPhaseTool:
    name = "skills_load_for_phase"
    description = "Load full skill instructions for a phase after metadata routing."
    parameters = {
        "type": "object",
        "properties": {
            "phase": {"type": "string", "description": "Harness phase."},
            "topic": {"type": "string", "description": "Current topic.", "default": ""},
            "roles": {"type": "array", "items": {"type": "string"}, "description": "Optional role override."},
        },
        "required": ["phase"],
    }

    def __init__(self, manager: SkillManager, trace: SkillTraceRecorder, router: SkillRouter | None = None):
        self.manager = manager
        self.trace = trace
        self.router = router

    async def execute(self, phase: str, topic: str = "", roles: list[str] | None = None) -> str:
        if self.router is not None:
            role_list = roles or PHASE_ROLES.get(phase, [])
            decision = self.router.route(phase=phase, topic=topic, candidates=self.manager.list(), roles=role_list)
            context = self.manager.load_names(decision.selected_names, phase=phase)
        else:
            context = self.manager.load_for_phase(phase, extra_roles=roles)
        injected_chars = sum(len(skill.content) for skill in context.active)
        self.trace.record(
            phase=phase,
            action="load",
            skill_names=context.names,
            roles=sorted({role for skill in context.active for role in skill.metadata.roles}),
            reason="loaded full skill instructions after phase selection",
            injected_chars=injected_chars,
            resources=[f"{skill.name}:{resource}" for skill in context.active for resource in skill.loaded_resources],
        )
        return json.dumps({"phase": phase, "loaded_skills": context.names, "context": context.render()}, ensure_ascii=False)


class SkillUnloadTool:
    name = "skills_unload"
    description = "Unload currently active skills after a phase finishes."
    parameters = {"type": "object", "properties": {}}

    def __init__(self, manager: SkillManager, trace: SkillTraceRecorder):
        self.manager = manager
        self.trace = trace

    async def execute(self) -> str:
        before = self.manager.unload()
        self.trace.record(phase="manual", action="unload", skill_names=before, reason="agent unloaded active skill context")
        return json.dumps({"unloaded": before}, ensure_ascii=False)


class SkillResourceIndexTool:
    name = "skills_resource_index"
    description = "List references, templates, assets, config files, and scripts available inside a skill."
    parameters = {
        "type": "object",
        "properties": {"name": {"type": "string", "description": "Skill name."}},
        "required": ["name"],
    }

    def __init__(self, manager: SkillManager, trace: SkillTraceRecorder):
        self.manager = manager
        self.trace = trace

    async def execute(self, name: str) -> str:
        resources = self.manager.resource_index(name)
        self.trace.record(phase="manual", action="resource_index", skill_names=[name], resources=[str(item["path"]) for item in resources])
        return json.dumps(resources, ensure_ascii=False)


class SkillReadResourceTool:
    name = "skills_read_resource"
    description = "Read an on-demand skill resource by relative path."
    parameters = {
        "type": "object",
        "properties": {
            "name": {"type": "string", "description": "Skill name."},
            "relative_path": {"type": "string", "description": "Resource path relative to the skill root."},
            "max_chars": {"type": "integer", "default": 12000},
        },
        "required": ["name", "relative_path"],
    }

    def __init__(self, manager: SkillManager, trace: SkillTraceRecorder):
        self.manager = manager
        self.trace = trace

    async def execute(self, name: str, relative_path: str, max_chars: int = 12000) -> str:
        text = self.manager.read_resource(name, relative_path, max_chars=max_chars)
        self.trace.record(phase="manual", action="read_resource", skill_names=[name], resources=[relative_path], injected_chars=len(text))
        return text


class SkillRunScriptTool:
    name = "skills_run_script"
    description = "Run an enabled external skill script with explicit arguments."
    parameters = {
        "type": "object",
        "properties": {
            "name": {"type": "string", "description": "Skill name."},
            "relative_path": {"type": "string", "description": "Script path relative to skill root."},
            "args": {"type": "array", "items": {"type": "string"}, "default": []},
            "timeout_seconds": {"type": "integer", "default": 60},
        },
        "required": ["name", "relative_path"],
    }

    def __init__(self, manager: SkillManager, trace: SkillTraceRecorder):
        self.manager = manager
        self.trace = trace

    async def execute(
        self,
        name: str,
        relative_path: str,
        args: list[str] | None = None,
        timeout_seconds: int = 60,
    ) -> str:
        result = self.manager.run_script(name, relative_path, args=args or [], timeout_seconds=timeout_seconds)
        self.trace.record(
            phase="manual",
            action="run_script",
            skill_names=[name],
            scripts=[relative_path],
            metadata={"returncode": result.get("returncode")},
        )
        return json.dumps(result, ensure_ascii=False)


def register_skill_tools(registry: Any, manager: SkillManager, router: SkillRouter, trace: SkillTraceRecorder) -> None:
    registry.register(SkillListIndexTool(manager, trace))
    registry.register(SkillRouteForPhaseTool(manager, router, trace))
    registry.register(SkillLoadForPhaseTool(manager, trace, router))
    registry.register(SkillUnloadTool(manager, trace))
    registry.register(SkillResourceIndexTool(manager, trace))
    registry.register(SkillReadResourceTool(manager, trace))
    registry.register(SkillRunScriptTool(manager, trace))
