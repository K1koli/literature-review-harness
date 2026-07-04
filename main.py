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
import sys

from src.utils.config import Config
from src.llm.client import LLMClient
from src.tools.registry import ToolRegistry
from src.tools.sciverse_tools import SearchLiteratureTool, ReadContextTool
from src.agent.context import ContextBuilder
from src.agent.loop import AgentLoop


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

    registry = ToolRegistry()
    registry.register(SearchLiteratureTool(config.sciverse_api_token))
    registry.register(ReadContextTool(config.sciverse_api_token))

    context = ContextBuilder()

    loop = AgentLoop(
        llm=llm,
        registry=registry,
        context=context,
        max_iterations=config.max_iterations,
        verbose=True,
    )

    # Allow user to specify a custom topic via command line
    if len(sys.argv) > 1:
        topic = " ".join(sys.argv[1:])
    else:
        topic = "World Models（世界模型）in deep learning and reinforcement learning"

    user_message = (
        f"Please generate a comprehensive academic literature survey on the following topic: "
        f"\"{topic}\". \n\n"
        "Steps:\n"
        "1. Search for papers using multiple diverse queries covering different sub-topics.\n"
        "2. Read the full context of the most relevant papers.\n"
        "3. Write a structured survey with proper inline citations [doc_id, offset].\n"
        "Output in well-formatted Markdown."
    )

    result = await loop.run(user_message)

    # Save output
    output_path = "output/survey.md"
    import os
    os.makedirs("output", exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(result)

    print(f"\n{'=' * 60}")
    print(f"Survey saved to {output_path}")
    print(f"Total characters: {len(result)}")

    await llm.close()


if __name__ == "__main__":
    asyncio.run(main())
