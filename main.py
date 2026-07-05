#!/usr/bin/env python3
"""Literature Review Harness — Entry point.

Usage:
    python main.py

Set environment variables in .env:
    INTERN_API_BASE   — Intern-S2-Preview API base URL
    INTERN_API_KEY    — Intern-S2-Preview API key
    SCIVERSE_API_TOKEN — Sciverse API token (starts with 'sv-')
"""

import asyncio
import json
import os
import sys
from pathlib import Path

from src.agent.context import ContextBuilder
from src.agent.loop import AgentLoop
from src.exporters import export_html, export_latex
from src.images.pipeline import generate_survey_images
from src.llm.client import LLMClient
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
from src.tools.mineru import MinerUConfig, MINERU_FAST_PAGE_RANGES
from src.tools.registry import ToolRegistry
from src.tools.survey_context import PrepareSurveyContextTool
from src.utils.config import Config
from src.utils.runs import create_run_paths, sync_latest_compat_outputs, write_latest_pointer
from src.validation.citations import CitationVerifier
from src.validation.repair import repair_missing_evidence_citations
from src.validation.multi_agent import MultiAgentReviewer
from src.skill_system.manager import SkillManager
from src.skill_system.router import SkillRouter
from src.skill_system.tools import register_skill_tools
from src.skill_system.trace import SkillTraceRecorder


async def main():
    config = Config.from_env()
    errors = config.validate()
    if errors:
        print("Configuration errors:")
        for e in errors:
            print(f"  - {e}")
        print("\nRename .env.example to .env and fill in your API keys.")
        sys.exit(1)

    # Allow user to specify a custom topic via command line
    if len(sys.argv) > 1:
        topic = " ".join(sys.argv[1:])
    else:
        topic = "World Models（世界模型）in deep learning and reinforcement learning"
    run_paths = create_run_paths(topic)

    # Build components
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
    project_root = Path(__file__).resolve().parent
    skills_enabled = os.getenv("SKILLS_ENABLED", "true").lower() in {"1", "true", "yes", "on"}
    skill_trace = None
    skill_manager = None
    skill_router = None
    if skills_enabled:
        skills_config = Path(os.getenv("SKILLS_CONFIG", "configs/skills.toml"))
        if not skills_config.is_absolute():
            skills_config = project_root / skills_config
        skill_trace_path = Path(os.getenv("SKILLS_TRACE_PATH") or str(run_paths.skill_trace))
        if not skill_trace_path.is_absolute():
            skill_trace_path = project_root / skill_trace_path
        skill_manager = SkillManager(project_root / "skills", external_config=skills_config)
        skill_router = SkillRouter()
        skill_trace = SkillTraceRecorder(skill_trace_path)
        register_skill_tools(registry, skill_manager, skill_router, skill_trace)

    verifier = CitationVerifier(kb)
    reviewer = MultiAgentReviewer(
        llm,
        kb,
        topic=topic,
        enabled=os.getenv("MULTI_AGENT_ENABLED", "true").lower() in {"1", "true", "yes", "on"},
        timeout_seconds=int(os.getenv("MULTI_AGENT_REVIEW_TIMEOUT", "45")),
    )

    loop = AgentLoop(
        llm=llm,
        registry=registry,
        context=context,
        max_iterations=config.max_iterations,
        verbose=True,
    )
    loop.add_stop_condition(verifier)
    loop.add_stop_condition(reviewer)

    user_message = (
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

    try:
        result = await loop.run(user_message)
    finally:
        await llm.close()
        if skill_trace is not None:
            skill_trace.save()

    # Save output and audit artifacts.
    output_dir = run_paths.run_dir
    os.makedirs(output_dir, exist_ok=True)
    survey_path = run_paths.survey_md
    evidence_path = run_paths.evidence_pack
    check_path = run_paths.check_report
    result = repair_missing_evidence_citations(result, kb)
    verifier.last_report = verifier.validate_text(result)
    with open(survey_path, "w", encoding="utf-8") as f:
        f.write(result)
    with open(evidence_path, "w", encoding="utf-8") as f:
        f.write(kb.to_json())
    with open(check_path, "w", encoding="utf-8") as f:
        json.dump(verifier.report_dict(), f, ensure_ascii=False, indent=2)

    figure_skill_guidance = ""
    if skill_manager is not None and skill_router is not None and skill_trace is not None:
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
        if decision.selected_names:
            figure_context = skill_manager.load_names(decision.selected_names, phase="figure")
            figure_skill_guidance = figure_context.render()
            skill_trace.record(
                phase="figure",
                action="load",
                skill_names=figure_context.names,
                roles=decision.roles,
                reason="loaded figure skill guidance for image prompt construction",
                injected_chars=len(figure_skill_guidance),
                resources=[f"{skill.name}:{resource}" for skill in figure_context.active for resource in skill.loaded_resources],
            )
            unloaded = skill_manager.unload()
            skill_trace.record(
                phase="figure",
                action="unload",
                skill_names=unloaded,
                reason="cleared figure skill guidance after prompt construction",
            )

    image_result = await generate_survey_images(
        config=config,
        topic=topic,
        survey_markdown=result,
        kb=kb,
        output_dir=output_dir,
        survey_path=survey_path,
        figures_dir=run_paths.figures_dir,
        figure_plan_path=run_paths.figure_plan,
        skill_guidance=figure_skill_guidance,
    )
    if skill_trace is not None:
        skill_trace.save()
    html_path = run_paths.survey_html
    tex_path = run_paths.survey_tex
    export_html(survey_path, html_path, title=topic)
    export_latex(survey_path, tex_path, title=topic)
    write_latest_pointer(run_paths)
    sync_latest_compat_outputs(run_paths)

    print(f"\n{'=' * 60}")
    print(f"Run directory: {run_paths.run_dir}")
    print(f"Survey saved to {survey_path}")
    print(f"HTML survey saved to {html_path}")
    print(f"LaTeX survey saved to {tex_path}")
    print(f"Evidence pack saved to {evidence_path}")
    print(f"Check report saved to {check_path}")
    if image_result.enabled:
        print(f"Generated images: {len(image_result.generated)}")
        if image_result.manifest_path:
            print(f"Image manifest saved to {image_result.manifest_path}")
        if image_result.errors:
            print(f"Image generation errors: {len(image_result.errors)}")
    else:
        print(f"Image generation skipped: {image_result.skipped_reason}")
    if skill_trace is not None:
        print(f"Skill trace saved to {skill_trace.output_path}")
    print(f"Total characters: {len(result)}")


if __name__ == "__main__":
    asyncio.run(main())
