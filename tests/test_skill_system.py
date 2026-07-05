from __future__ import annotations

import asyncio
import tempfile
import unittest
from pathlib import Path

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

    def test_configured_nested_skill_path_can_be_loaded_without_recursive_scan(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            nested = root / "skills" / "third-party-pack" / "skills" / "figure-generation"
            nested.mkdir(parents=True)
            (nested / "SKILL.md").write_text(
                "---\n"
                "name: upstream-figure-generation\n"
                "description: Figure generation protocol.\n"
                "---\n\n"
                "# Upstream Figure Generation\n\n"
                "Build evidence-grounded figure briefs.",
                encoding="utf-8",
            )
            config = root / "configs" / "skills.toml"
            config.parent.mkdir()
            config.write_text(
                '[[skills]]\n'
                'name = "configured-figure-generation"\n'
                'path = "skills/third-party-pack/skills/figure-generation"\n'
                'roles = ["figure_planning", "figure_generation"]\n'
                'enabled = true\n'
                'allow_scripts = false\n'
                'max_chars = 2000\n',
                encoding="utf-8",
            )

            manager = SkillManager(root / "skills", external_config=config)
            figure_context = manager.load_for_phase("figure")

            self.assertIn("configured-figure-generation", figure_context.names)
            self.assertIn("Build evidence-grounded figure briefs", figure_context.render())

    def test_configured_skill_paths_outside_skills_are_ignored(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            inside = root / "skills" / "inside-skill"
            outside = root / "external_skills" / "outside-skill"
            inside.mkdir(parents=True)
            outside.mkdir(parents=True)
            (inside / "SKILL.md").write_text(
                "---\n"
                "name: inside-skill\n"
                "description: Inside skill.\n"
                "---\n\n"
                "# Inside Skill\n",
                encoding="utf-8",
            )
            (outside / "SKILL.md").write_text(
                "---\n"
                "name: outside-skill\n"
                "description: Outside skill.\n"
                "---\n\n"
                "# Outside Skill\n",
                encoding="utf-8",
            )
            config = root / "configs" / "skills.toml"
            config.parent.mkdir()
            config.write_text(
                '[[skills]]\n'
                'name = "configured-inside"\n'
                'path = "skills/inside-skill"\n'
                'roles = ["survey_writing"]\n'
                'enabled = true\n\n'
                '[[skills]]\n'
                'name = "configured-outside"\n'
                'path = "external_skills/outside-skill"\n'
                'roles = ["survey_writing"]\n'
                'enabled = true\n',
                encoding="utf-8",
            )

            manager = SkillManager(root / "skills", external_config=config)
            names = {meta.name for meta in manager.list()}

            self.assertIn("inside-skill", names)
            self.assertIn("configured-inside", names)
            self.assertNotIn("configured-outside", names)
            self.assertNotIn("outside-skill", names)

    def test_router_caps_phase_skill_selection(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            skills_root = root / "skills"
            for name, role in [
                ("research-framing", "research_framing"),
                ("survey-writing", "survey_writing"),
                ("citation-grounding", "citation_grounding"),
                ("external-literature", "research_framing"),
                ("external-survey", "survey_writing"),
                ("external-related", "survey_writing"),
            ]:
                skill_dir = skills_root / name
                skill_dir.mkdir(parents=True)
                (skill_dir / "SKILL.md").write_text(
                    f"---\nname: {name}\nroles: [{role}]\ndescription: {name}\n---\n\n# {name}\n",
                    encoding="utf-8",
                )

            manager = SkillManager(skills_root)
            decision = SkillRouter().route(
                phase="literature_review",
                topic="World Models",
                candidates=manager.list(),
                roles=["research_framing", "survey_writing", "citation_grounding"],
            )

            self.assertLessEqual(len(decision.selected_names), 4)
            self.assertIn("citation-grounding", decision.selected_names)


if __name__ == "__main__":
    unittest.main()
