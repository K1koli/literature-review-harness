from __future__ import annotations

import asyncio
import json
import tempfile
import unittest
from pathlib import Path

from src.skill_system.injection import SkillContextInjector
from src.skill_system.manager import SkillManager
from src.skill_system.router import SkillRouter
from src.skill_system.tools import (
    SkillListIndexTool,
    SkillLoadForPhaseTool,
    SkillRouteForPhaseTool,
    SkillUnloadTool,
)
from src.skill_system.trace import SkillTraceRecorder


PROJECT_ROOT = Path(__file__).resolve().parents[1]


class SkillSystemTest(unittest.TestCase):
    def test_discovers_builtin_skill_metadata_without_loading_content(self) -> None:
        manager = SkillManager(PROJECT_ROOT / "skills")
        metas = manager.list()
        names = {meta.name for meta in metas}

        self.assertIn("research-framing", names)
        self.assertIn("survey-writing", names)
        self.assertIn("citation-grounding", names)
        self.assertEqual(manager.active_names, [])

    def test_routes_then_loads_and_unloads_phase_skills(self) -> None:
        manager = SkillManager(PROJECT_ROOT / "skills")
        router = SkillRouter()
        decision = router.route(
            phase="literature_review",
            topic="World Models",
            candidates=manager.list(),
            roles=["research_framing", "survey_writing", "citation_grounding"],
        )

        self.assertIn("survey-writing", decision.selected_names)
        self.assertEqual(manager.active_names, [])

        context = manager.load_names(decision.selected_names, phase="literature_review")
        self.assertIn("Survey Writing Skill", context.render())
        self.assertIn("citation-grounding", context.names)

        unloaded = manager.unload()
        self.assertEqual(set(unloaded), set(context.names))
        self.assertEqual(manager.active_names, [])

    def test_injector_adds_skill_context_and_writes_trace(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            trace = SkillTraceRecorder(Path(tmp) / "skill_trace.json")
            manager = SkillManager(PROJECT_ROOT / "skills")
            injector = SkillContextInjector(
                manager,
                SkillRouter(),
                trace,
                phase="literature_review",
                topic="World Models",
            )

            messages = [{"role": "system", "content": "base"}, {"role": "user", "content": "write"}]
            injected, tools = injector(messages, [])
            injector.unload()
            trace.save()

            self.assertEqual(tools, [])
            self.assertEqual(len(injected), len(messages))
            self.assertIn("Loaded Skill Protocols", injected[0]["content"])

            data = json.loads((Path(tmp) / "skill_trace.json").read_text(encoding="utf-8"))
            actions = {item["action"] for item in data}
            self.assertTrue({"discover", "route", "load", "inject", "unload"} <= actions)

    def test_skill_tools_expose_progressive_disclosure_steps(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            manager = SkillManager(PROJECT_ROOT / "skills")
            router = SkillRouter()
            trace = SkillTraceRecorder(Path(tmp) / "skill_trace.json")

            index = asyncio.run(SkillListIndexTool(manager, trace).execute())
            routed = asyncio.run(SkillRouteForPhaseTool(manager, router, trace).execute("literature_review", "World Models"))
            loaded = asyncio.run(SkillLoadForPhaseTool(manager, trace).execute("literature_review"))
            unloaded = asyncio.run(SkillUnloadTool(manager, trace).execute())

            self.assertIn("survey-writing", index)
            self.assertIn("survey-writing", routed)
            self.assertIn("Survey Writing Skill", loaded)
            self.assertIn("survey-writing", unloaded)


if __name__ == "__main__":
    unittest.main()
