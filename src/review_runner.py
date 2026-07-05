from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

from src.agent.context import ContextBuilder
from src.agent.loop import AgentLoop
from src.exporters import export_html, export_latex
from src.images.pipeline import ImageGenerationResult, generate_survey_images
from src.llm.client import LLMClient
from src.skill_system.manager import SkillManager
from src.skill_system.router import SkillRouter
from src.skill_system.tools import register_skill_tools
from src.skill_system.trace import SkillTraceRecorder
from src.state.kb import LiteratureKB
from src.tools.literature_kb import (
    BuildLiteratureKBTool,
    ListEvidenceTool,
    ListParsedPapersTool,
    ReadContextTool,
    ReadEvidenceTool,
    ReadParsedPaperTool,
    SearchLiteratureTool,
    SearchParsedPaperTool,
)
from src.tools.mineru import MINERU_FAST_PAGE_RANGES, MinerUConfig
from src.tools.registry import ToolRegistry
from src.tools.survey_context import PrepareSurveyContextTool
from src.utils.config import Config
from src.utils.runs import create_run_paths, sync_latest_compat_outputs, write_latest_pointer
from src.validation.citations import CitationVerifier
from src.validation.multi_agent import MultiAgentReviewer
from src.validation.references import format_numbered_references
from src.validation.repair import repair_missing_evidence_citations


PROJECT_ROOT = Path(__file__).resolve().parents[1]
ReviewEventSink = Callable[[dict[str, Any]], None]


class ConfigError(RuntimeError):
    def __init__(self, errors: list[str]):
        self.errors = errors
        super().__init__("; ".join(errors))


@dataclass(frozen=True)
class ReviewArtifacts:
    topic: str
    output_root: Path
    run_dir: Path
    survey_path: Path
    html_path: Path
    tex_path: Path
    evidence_path: Path
    check_path: Path
    skill_trace_path: Path | None
    figure_plan_path: Path
    figures_dir: Path
    image_result: ImageGenerationResult
    report: dict[str, Any]
    total_characters: int


def build_review_prompt(topic: str) -> str:
    return (
        f"Please generate a comprehensive academic literature survey on the following topic: "
        f"\"{topic}\". \n\n"
        "Required workflow:\n"
        "1. First call build_literature_kb with a broad query for the topic.\n"
        "2. Use list_evidence/read_evidence and optional follow-up search_literature/read_context calls.\n"
        "3. Seek coverage for definitions, organizing frameworks, major method families, applications, evaluation, "
        "limitations, and future directions.\n"
        "4. If Sciverse snippets are not enough for a key claim or comparison, use list_parsed_papers plus "
        "read_parsed_paper/search_parsed_paper to inspect MinerU parsed original-paper text and create citeable evidence ids.\n"
        "5. If skill tools are available, you must demonstrate progressive-disclosure skill use before final drafting: "
        "call skills_list_index, route/load only the needed write or literature_review skills, use the loaded instructions "
        "as writing protocols rather than factual evidence, then call skills_unload after the guidance has been absorbed.\n"
        "6. Call prepare_survey_context to organize the retrieved evidence and design a survey structure. "
        "If its survey_design.evidence_needs show missing support, make a small number of targeted "
        "search_literature/read_context/parsed-paper calls before writing; do not repeatedly re-run planning.\n"
        "7. Then write the complete survey directly in your assistant response. Every substantive paragraph must cite "
        "existing evidence ids such as [P001-E01]. Do not stop at an outline, notes, or an evidence summary."
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

    output_root = Path(output_dir)
    if not output_root.is_absolute():
        output_root = PROJECT_ROOT / output_root
    run_paths = create_run_paths(topic, output_root=output_root)

    _emit(
        event_sink,
        "components_build_started",
        topic=topic,
        output_dir=str(run_paths.run_dir),
        model=config.model,
        mineru_enabled=config.mineru_enabled and bool(config.mineru_api_token),
        image_generation_enabled=config.image_generation_enabled,
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
    registry.register(ListParsedPapersTool(kb))
    registry.register(ReadParsedPaperTool(kb))
    registry.register(SearchParsedPaperTool(kb))
    registry.register(PrepareSurveyContextTool(kb, llm=llm))

    context = ContextBuilder()
    context.add_post_tool_hook(lambda result: (result[:6000] + "\n...(truncated)") if len(result) > 6500 else result)
    skills_enabled = os.getenv("SKILLS_ENABLED", "true").lower() in {"1", "true", "yes", "on"}
    skill_trace: SkillTraceRecorder | None = None
    skill_manager: SkillManager | None = None
    skill_router: SkillRouter | None = None
    if skills_enabled:
        skills_config = Path(os.getenv("SKILLS_CONFIG", "configs/skills.toml"))
        if not skills_config.is_absolute():
            skills_config = PROJECT_ROOT / skills_config
        skill_trace_path = Path(os.getenv("SKILLS_TRACE_PATH") or str(run_paths.skill_trace))
        if not skill_trace_path.is_absolute():
            skill_trace_path = PROJECT_ROOT / skill_trace_path
        skill_manager = SkillManager(PROJECT_ROOT / "skills", external_config=skills_config)
        skill_router = SkillRouter()
        skill_trace = SkillTraceRecorder(skill_trace_path)
        register_skill_tools(registry, skill_manager, skill_router, skill_trace)
        _emit(event_sink, "skill_system_enabled", skill_count=len(skill_manager.list()))
    else:
        _emit(event_sink, "skill_system_disabled")

    ma_enabled = os.getenv("MULTI_AGENT_ENABLED", "true").lower() in {"1", "true", "yes", "on"}
    verifier = CitationVerifier(kb)
    reviewer = MultiAgentReviewer(
        llm,
        kb,
        topic=topic,
        enabled=ma_enabled,
        timeout_seconds=int(os.getenv("MULTI_AGENT_REVIEW_TIMEOUT", "45")),
    )
    _emit(event_sink, "multi_agent_review_configured", enabled=ma_enabled)
    loop = AgentLoop(
        llm=llm,
        registry=registry,
        context=context,
        max_iterations=config.max_iterations,
        verbose=verbose,
        event_sink=event_sink,
    )
    loop.add_stop_condition(verifier)
    loop.add_stop_condition(reviewer)

    _emit(event_sink, "components_ready", tools=registry.list_names())
    try:
        result = await loop.run(build_review_prompt(topic))
    finally:
        await llm.close()
        if skill_trace is not None:
            skill_trace.save()

    survey_path = run_paths.survey_md
    evidence_path = run_paths.evidence_pack
    check_path = run_paths.check_report
    result = repair_missing_evidence_citations(result, kb)
    verifier.last_report = verifier.validate_text(result)
    survey_path.write_text(result, encoding="utf-8")
    evidence_path.write_text(kb.to_json(), encoding="utf-8")
    report = verifier.report_dict()
    check_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    figure_skill_guidance = _load_figure_skill_guidance(
        topic=topic,
        skill_trace=skill_trace,
        skill_manager=skill_manager if skills_enabled else None,
        skill_router=skill_router if skills_enabled else None,
    )
    _emit(event_sink, "image_generation_started", enabled=config.image_generation_enabled)
    image_result = await generate_survey_images(
        config=config,
        topic=topic,
        survey_markdown=result,
        kb=kb,
        output_dir=run_paths.run_dir,
        survey_path=survey_path,
        figures_dir=run_paths.figures_dir,
        figure_plan_path=run_paths.figure_plan,
        skill_guidance=figure_skill_guidance,
    )
    _emit(
        event_sink,
        "image_generation_finished",
        enabled=image_result.enabled,
        generated=len(image_result.generated),
        skipped_reason=image_result.skipped_reason,
        errors=image_result.errors,
    )
    if skill_trace is not None:
        skill_trace.save()

    formatted_result = format_numbered_references(survey_path.read_text(encoding="utf-8"), kb)
    survey_path.write_text(formatted_result, encoding="utf-8")
    html_path = run_paths.survey_html
    tex_path = run_paths.survey_tex
    export_html(survey_path, html_path, title=topic)
    export_latex(survey_path, tex_path, title=topic)
    write_latest_pointer(run_paths)
    sync_latest_compat_outputs(run_paths)
    final_survey = survey_path.read_text(encoding="utf-8")
    _emit(
        event_sink,
        "artifacts_written",
        survey_path=str(survey_path),
        html_path=str(html_path),
        tex_path=str(tex_path),
        evidence_path=str(evidence_path),
        check_path=str(check_path),
        figure_plan_path=str(run_paths.figure_plan),
        figures_dir=str(run_paths.figures_dir),
        citation_status=report.get("status"),
        total_characters=len(final_survey),
    )

    return ReviewArtifacts(
        topic=topic,
        output_root=output_root,
        run_dir=run_paths.run_dir,
        survey_path=survey_path,
        html_path=html_path,
        tex_path=tex_path,
        evidence_path=evidence_path,
        check_path=check_path,
        skill_trace_path=skill_trace.output_path if skill_trace is not None else None,
        figure_plan_path=run_paths.figure_plan,
        figures_dir=run_paths.figures_dir,
        image_result=image_result,
        report=report,
        total_characters=len(final_survey),
    )


def _emit(event_sink: ReviewEventSink | None, event_type: str, **payload: Any) -> None:
    if event_sink is None:
        return
    event_sink({"type": event_type, **payload})


def _load_figure_skill_guidance(
    *,
    topic: str,
    skill_trace: SkillTraceRecorder | None,
    skill_manager: SkillManager | None,
    skill_router: SkillRouter | None,
) -> str:
    if skill_manager is None or skill_router is None or skill_trace is None:
        return ""
    available = skill_manager.list()
    decision = skill_router.route(
        phase="figure",
        topic=topic,
        candidates=available,
        roles=["figure_planning", "figure_generation", "figure_verification"],
    )
    skill_trace.record(
        phase="figure",
        action="route",
        skill_names=decision.selected_names,
        roles=decision.roles,
        reason=decision.reason,
        metadata={"available_skills": decision.available_names},
    )
    if not decision.selected_names:
        return ""
    figure_context = skill_manager.load_names(decision.selected_names, phase="figure")
    guidance = figure_context.render()
    skill_trace.record(
        phase="figure",
        action="load",
        skill_names=figure_context.names,
        roles=decision.roles,
        reason="loaded figure skill guidance for image prompt construction",
        injected_chars=len(guidance),
        resources=[f"{skill.name}:{resource}" for skill in figure_context.active for resource in skill.loaded_resources],
    )
    unloaded = skill_manager.unload()
    skill_trace.record(
        phase="figure",
        action="unload",
        skill_names=unloaded,
        reason="cleared figure skill guidance after prompt construction",
    )
    return guidance
