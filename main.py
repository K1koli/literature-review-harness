#!/usr/bin/env python3
"""Literature Review Harness CLI entry point."""

import asyncio
import sys
from pathlib import Path

from src.review_runner import ConfigError, run_literature_review


async def main() -> None:
    topic = (
        " ".join(sys.argv[1:])
        if len(sys.argv) > 1
        else "World Models（世界模型）in deep learning and reinforcement learning"
    )

    try:
        artifacts = await run_literature_review(topic, output_dir=Path("output"), verbose=True)
    except ConfigError as exc:
        print("Configuration errors:")
        for error in exc.errors:
            print(f"  - {error}")
        print("\nRename .env.example to .env and fill in your API keys.")
        sys.exit(1)

    print(f"\n{'=' * 60}")
    print(f"Run directory: {artifacts.run_dir}")
    print(f"Survey saved to {artifacts.survey_path}")
    print(f"HTML survey saved to {artifacts.html_path}")
    print(f"LaTeX survey saved to {artifacts.tex_path}")
    print(f"Evidence pack saved to {artifacts.evidence_path}")
    print(f"Check report saved to {artifacts.check_path}")
    if artifacts.image_result.enabled:
        print(f"Generated images: {len(artifacts.image_result.generated)}")
        if artifacts.image_result.manifest_path:
            print(f"Image manifest saved to {artifacts.image_result.manifest_path}")
        if artifacts.image_result.errors:
            print(f"Image generation errors: {len(artifacts.image_result.errors)}")
    else:
        print(f"Image generation skipped: {artifacts.image_result.skipped_reason}")
    if artifacts.skill_trace_path is not None:
        print(f"Skill trace saved to {artifacts.skill_trace_path}")
    print(f"Total characters: {artifacts.total_characters}")


if __name__ == "__main__":
    asyncio.run(main())
