from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

from src.agent.context import ContextBuilder
from src.agent.loop import AgentLoop
from src.llm.client import LLMClient
from src.skill_system.injection import SkillContextInjector
from src.skill_system.manager import SkillManager
from src.skill_system.router import SkillRouter
from src.skill_system.tools import register_skill_tools
from src.skill_system.trace import SkillTraceRecorder
from src.state.kb import LiteratureKB
from src.tools.literature_kb import (
    BuildLiteratureKBTool,
    ListEvidenceTool,
    ReadContextTool,
    ReadEvidenceTool,
    SearchLiteratureTool,
)
from src.tools.mineru import MINERU_FAST_PAGE_RANGES, MinerUConfig
from src.tools.registry import ToolRegistry
from src.utils.config import Config
from src.validation.citations import CitationVerifier


PROJECT_ROOT = Path(__file__).resolve().parents[1]
ReviewEventSink = Callable[[dict[str, Any]], None]


class ConfigError(RuntimeError):
    def __init__(self, errors: list[str]):
        self.errors = errors
        super().__init__("; ".join(errors))


@dataclass(frozen=True)
class ReviewArtifacts:
    topic: str
    output_dir: Path
    survey_path: Path
    evidence_path: Path
    check_path: Path
    skill_trace_path: Path | None
    report: dict[str, Any]
    total_characters: int


def build_review_prompt(topic: str) -> str:
    return (
        f"Please generate a comprehensive academic literature survey on the following topic: "
        f"\"{topic}\". \n\n"
        "Steps:\n"
        "1. First call build_literature_kb with a broad query for the topic.\n"
        "2. Use list_evidence/read_evidence and optional follow-up search_literature/read_context calls.\n"
        "3. Write a structured academic survey whose substantive paragraphs cite evidence ids like [P001-E01].\n"
        "Output in well-formatted Markdown."
    )


async def run_literature_review(
    topic: str,
    *,
    output_dir: str | Path = PROJECT_ROOT / "output",
    config: Config | None = None,
    verbose: bool = True,
    event_sink: ReviewEventSink | None = None,
) -> ReviewArtifacts:
    config = config or Config.from_env()
    errors = config.validate()
    if errors:
        _emit(event_sink, "config_error", errors=errors)
        raise ConfigError(errors)

    output_path = Path(output_dir)
    if not output_path.is_absolute():
        output_path = PROJECT_ROOT / output_path
    output_path.mkdir(parents=True, exist_ok=True)

    _emit(
        event_sink,
        "components_build_started",
        topic=topic,
        output_dir=str(output_path),
        model=config.model,
        mineru_enabled=config.mineru_enabled and bool(config.mineru_api_token),
    )

    llm = LLMClient(config.intern_api_base, config.intern_api_key, config.model)
    kb = LiteratureKB()
    mineru_config = MinerUConfig(
        api_token=config.mineru_api_token,
        enabled=config.mineru_enabled and bool(config.mineru_api_token),
        timeout_seconds=config.mineru_timeout,
        batch_size=config.mineru_batch_size,
        page_ranges=MINERU_FAST_PAGE_RANGES if config.mineru_fast else "",
        enable_table=False if config.mineru_fast else True,
        enable_formula=False if config.mineru_fast else True,
    )

    registry = ToolRegistry()
    registry.register(BuildLiteratureKBTool(config.sciverse_api_token, kb, mineru_config))
    registry.register(ListEvidenceTool(kb))
    registry.register(ReadEvidenceTool(kb))
    registry.register(SearchLiteratureTool(config.sciverse_api_token, kb))
    registry.register(ReadContextTool(config.sciverse_api_token, kb))

    context = ContextBuilder()
    skills_enabled = os.getenv("SKILLS_ENABLED", "true").lower() in {"1", "true", "yes", "on"}
    skill_trace: SkillTraceRecorder | None = None
    skill_injector: SkillContextInjector | None = None
    if skills_enabled:
        skills_config = Path(os.getenv("SKILLS_CONFIG", "configs/skills.toml"))
        if not skills_config.is_absolute():
            skills_config = PROJECT_ROOT / skills_config
        skill_trace_path = output_path / "skill_trace.json"
        skill_manager = SkillManager(PROJECT_ROOT / "skills", external_config=skills_config)
        skill_router = SkillRouter()
        skill_trace = SkillTraceRecorder(skill_trace_path)
        skill_injector = SkillContextInjector(
            skill_manager,
            skill_router,
            skill_trace,
            phase="literature_review",
            topic=topic,
            enabled=True,
        )
        context.add_pre_llm_hook(skill_injector)
        register_skill_tools(registry, skill_manager, skill_router, skill_trace)
        _emit(event_sink, "skill_system_enabled", skill_count=len(skill_manager.list()))
    else:
        _emit(event_sink, "skill_system_disabled")

    verifier = CitationVerifier(kb)
    loop = AgentLoop(
        llm=llm,
        registry=registry,
        context=context,
        max_iterations=config.max_iterations,
        verbose=verbose,
        event_sink=event_sink,
    )
    loop.add_stop_condition(verifier)

    _emit(event_sink, "components_ready", tools=registry.list_names())
    try:
        result = await loop.run(build_review_prompt(topic))
    finally:
        await llm.close()
        if skill_injector is not None:
            skill_injector.unload()
        if skill_trace is not None:
            skill_trace.save()

    survey_path = output_path / "survey.md"
    evidence_path = output_path / "evidence_pack.json"
    check_path = output_path / "check_report.json"
    survey_path.write_text(result, encoding="utf-8")
    evidence_path.write_text(kb.to_json(), encoding="utf-8")
    report = verifier.report_dict()
    check_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    _emit(
        event_sink,
        "artifacts_written",
        survey_path=str(survey_path),
        evidence_path=str(evidence_path),
        check_path=str(check_path),
        citation_status=report.get("status"),
        total_characters=len(result),
    )

    return ReviewArtifacts(
        topic=topic,
        output_dir=output_path,
        survey_path=survey_path,
        evidence_path=evidence_path,
        check_path=check_path,
        skill_trace_path=skill_trace.output_path if skill_trace is not None else None,
        report=report,
        total_characters=len(result),
    )


def _emit(event_sink: ReviewEventSink | None, event_type: str, **payload: Any) -> None:
    if event_sink is None:
        return
    event_sink({"type": event_type, **payload})
