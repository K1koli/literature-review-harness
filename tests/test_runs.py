import json
import tempfile
import unittest
from datetime import datetime
from pathlib import Path

from src.utils.runs import create_run_paths, sync_latest_compat_outputs, write_latest_pointer


class RunPathsTest(unittest.TestCase):
    def test_create_run_paths_uses_timestamp_and_slug(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            paths = create_run_paths(
                "World Models（世界模型） in RL",
                output_root=Path(tmp) / "output",
                now=datetime(2026, 7, 5, 1, 23),
            )

            self.assertEqual(paths.run_dir.name, "20260705-0123-world-models-in-rl")
            self.assertEqual(paths.figures_dir.name, "figures")
            self.assertTrue(paths.run_dir.exists())
            self.assertTrue(paths.figures_dir.exists())

    def test_latest_pointer_and_compat_outputs_are_written(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            paths = create_run_paths("World Models", output_root=Path(tmp) / "output", now=datetime(2026, 7, 5, 1, 23))
            paths.survey_md.write_text("# Survey", encoding="utf-8")
            paths.survey_html.write_text("<html></html>", encoding="utf-8")
            paths.survey_tex.write_text("\\documentclass{article}", encoding="utf-8")
            paths.evidence_pack.write_text("{}", encoding="utf-8")
            paths.check_report.write_text("{}", encoding="utf-8")
            paths.skill_trace.write_text("[]", encoding="utf-8")
            paths.figure_plan.write_text("[]", encoding="utf-8")

            write_latest_pointer(paths)
            sync_latest_compat_outputs(paths)

            latest = json.loads((paths.output_root / "latest_run.json").read_text(encoding="utf-8"))
            self.assertEqual(latest["run_dir"], str(paths.run_dir))
            self.assertTrue((paths.output_root / "survey.md").exists())
            self.assertTrue((paths.output_root / "figure_plan.json").exists())


if __name__ == "__main__":
    unittest.main()
