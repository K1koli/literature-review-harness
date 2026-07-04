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

from src.agent.context import ContextBuilder
from src.agent.loop import AgentLoop
from src.llm.client import LLMClient
from src.state.kb import LiteratureKB
from src.tools.literature_kb import (
    BuildLiteratureKBTool,
    ListEvidenceTool,
    ReadContextTool,
    ReadEvidenceTool,
    SearchLiteratureTool,
)
from src.tools.mineru import MinerUConfig, MINERU_FAST_PAGE_RANGES
from src.tools.registry import ToolRegistry
from src.utils.config import Config
from src.validation.citations import CitationVerifier


async def main():
    config = Config.from_env()
    errors = config.validate()
    if errors:
        print("Configuration errors:")
        for e in errors:
            print(f"  - {e}")
        print("\nRename .env.example to .env and fill in your API keys.")
        sys.exit(1)

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

    context = ContextBuilder()
    verifier = CitationVerifier(kb)

    loop = AgentLoop(
        llm=llm,
        registry=registry,
        context=context,
        max_iterations=config.max_iterations,
        verbose=True,
    )
    loop.add_stop_condition(verifier)

    # Allow user to specify a custom topic via command line
    if len(sys.argv) > 1:
        topic = " ".join(sys.argv[1:])
    else:
        topic = "World Models（世界模型）in deep learning and reinforcement learning"

    user_message = (
        f"Please generate a comprehensive academic literature survey on the following topic: "
        f"\"{topic}\". \n\n"
        "Steps:\n"
        "1. First call build_literature_kb with a broad query for the topic.\n"
        "2. Use list_evidence/read_evidence and optional follow-up search_literature/read_context calls.\n"
        "3. Write a structured academic survey whose substantive paragraphs cite evidence ids like [P001-E01].\n"
        "Output in well-formatted Markdown."
    )

    try:
        result = await loop.run(user_message)
    finally:
        await llm.close()

    # Save output and audit artifacts.
    output_dir = "output"
    os.makedirs(output_dir, exist_ok=True)
    survey_path = os.path.join(output_dir, "survey.md")
    evidence_path = os.path.join(output_dir, "evidence_pack.json")
    check_path = os.path.join(output_dir, "check_report.json")
    with open(survey_path, "w", encoding="utf-8") as f:
        f.write(result)
    with open(evidence_path, "w", encoding="utf-8") as f:
        f.write(kb.to_json())
    with open(check_path, "w", encoding="utf-8") as f:
        json.dump(verifier.report_dict(), f, ensure_ascii=False, indent=2)

    print(f"\n{'=' * 60}")
    print(f"Survey saved to {survey_path}")
    print(f"Evidence pack saved to {evidence_path}")
    print(f"Check report saved to {check_path}")
    print(f"Total characters: {len(result)}")


if __name__ == "__main__":
    asyncio.run(main())
