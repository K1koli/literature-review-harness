from __future__ import annotations

import json
import re
import shutil
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path


@dataclass(frozen=True)
class RunPaths:
    output_root: Path
    run_dir: Path
    figures_dir: Path
    survey_md: Path
    survey_html: Path
    survey_tex: Path
    evidence_pack: Path
    check_report: Path
    skill_trace: Path
    figure_plan: Path


def create_run_paths(topic: str, *, output_root: Path = Path("output"), now: datetime | None = None) -> RunPaths:
    timestamp = (now or datetime.now()).strftime("%Y%m%d-%H%M")
    slug = _slugify(topic)
    run_dir = output_root / "runs" / f"{timestamp}-{slug}"
    figures_dir = run_dir / "figures"
    run_dir.mkdir(parents=True, exist_ok=True)
    figures_dir.mkdir(parents=True, exist_ok=True)
    return RunPaths(
        output_root=output_root,
        run_dir=run_dir,
        figures_dir=figures_dir,
        survey_md=run_dir / "survey.md",
        survey_html=run_dir / "survey.html",
        survey_tex=run_dir / "survey.tex",
        evidence_pack=run_dir / "evidence_pack.json",
        check_report=run_dir / "check_report.json",
        skill_trace=run_dir / "skill_trace.json",
        figure_plan=run_dir / "figure_plan.json",
    )


def write_latest_pointer(paths: RunPaths) -> None:
    paths.output_root.mkdir(parents=True, exist_ok=True)
    latest = {
        "run_dir": str(paths.run_dir),
        "survey_md": str(paths.survey_md),
        "survey_html": str(paths.survey_html),
        "survey_tex": str(paths.survey_tex),
        "evidence_pack": str(paths.evidence_pack),
        "check_report": str(paths.check_report),
        "skill_trace": str(paths.skill_trace),
        "figure_plan": str(paths.figure_plan),
        "figures_dir": str(paths.figures_dir),
    }
    (paths.output_root / "latest_run.json").write_text(json.dumps(latest, ensure_ascii=False, indent=2), encoding="utf-8")


def sync_latest_compat_outputs(paths: RunPaths) -> None:
    """Keep old output/survey.* paths available for existing local workflows."""

    for source, name in [
        (paths.survey_md, "survey.md"),
        (paths.survey_html, "survey.html"),
        (paths.survey_tex, "survey.tex"),
        (paths.evidence_pack, "evidence_pack.json"),
        (paths.check_report, "check_report.json"),
        (paths.skill_trace, "skill_trace.json"),
        (paths.figure_plan, "figure_plan.json"),
    ]:
        if source.exists():
            shutil.copyfile(source, paths.output_root / name)


def _slugify(value: str) -> str:
    slug = re.sub(r"[^A-Za-z0-9]+", "-", value.strip().lower()).strip("-")
    return slug[:64] or "survey"
