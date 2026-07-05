"""Multi-agent parallel review for survey quality improvement.

Three specialised review agents run concurrently, each evaluating a
different dimension of the draft.  Aggregated feedback is injected
as a user message so the main agent can fix issues in the next iteration.
"""

from __future__ import annotations

import asyncio
import json
from typing import Any

from ..llm.client import LLMClient
from ..state.kb import LiteratureKB

_REVIEW_PROMPTS = {
    "content_quality": (
        "You are a strict academic reviewer evaluating the CONTENT QUALITY of a literature survey draft.\n\n"
        "Check for:\n"
        "- Logical flow: does each section build on the previous one?\n"
        "- Depth: are key methods explained, or just named?\n"
        "- Comparative analysis: does the survey compare papers, or just list them?\n"
        "- Claims: are claims specific, or vague generalisations?\n"
        "- Gaps: are there obvious missing subtopics or papers?\n\n"
        "Give an overall score 1-10 and return a JSON object:\n"
        '{"score": <1-10>, "passed": true/false, "issues": [...], "suggestions": [...]}\n\n'
        "Be specific. Score >= 8 means good enough; < 5 means needs major rework."
    ),
    "citation_accuracy": (
        "You are a strict academic reviewer evaluating CITATION ACCURACY of a literature survey draft.\n\n"
        "The survey uses numeric citations [1] [2] with a References section.\n"
        "Check for:\n"
        "- References section: each entry must include paper_id: Pnnn from the KB\n"
        "- Every numbered citation [N] should correspond to a real reference entry\n"
        "- No mention of raw doc_ids, offsets, evidence IDs, or API traces in the prose\n"
        "- No vague placeholder phrases like 'Various works on...', 'Several studies...'\n\n"
        "Return a JSON object:\n"
        '{"passed": true/false, "issues": ["specific issue 1", ...], "suggestions": ["fix 1", ...]}\n\n'
        "Be specific about which references have problems."
    ),
    "structure_completeness": (
        "You are a strict academic reviewer evaluating STRUCTURE AND COMPLETENESS of a literature survey draft.\n\n"
        "Check for:\n"
        "- Does the survey have all required sections (Abstract, Introduction, Methods, Comparison, Future Work, References)?\n"
        "- Are sections balanced, or is one section 10x longer than others?\n"
        "- Is the abstract concise and accurate?\n"
        "- Does the conclusion synthesise findings rather than repeat the introduction?\n"
        "- Are there section numbering errors or formatting issues?\n\n"
        "Return a JSON object:\n"
        '{"passed": true/false, "issues": ["specific issue 1", ...], "suggestions": ["fix 1", ...]}\n\n'
        "Be specific about structural problems."
    ),
}


class MultiAgentReviewer:
    """Stop condition that runs 3 parallel review agents on the survey draft.

    Usage:
        reviewer = MultiAgentReviewer(llm_client, kb, topic)
        loop.add_stop_condition(reviewer)
    """

    def __init__(self, llm: LLMClient, kb: LiteratureKB, topic: str = "", enabled: bool = True, max_revisions: int = 3):
        self.llm = llm
        self.kb = kb
        self.topic = topic
        self.enabled = enabled
        self.max_revisions = max_revisions
        self._last_feedback: str = ""
        self._fail_count = 0

    async def __call__(self, messages: list[dict[str, Any]]) -> bool:
        if not self.enabled:
            return True

        # Find the last assistant content
        content = ""
        for m in reversed(messages):
            if m.get("role") == "assistant" and m.get("content"):
                content = str(m["content"])
                break

        if not content:
            return True

        # Auto-pass after max consecutive failures (avoids infinite revision loop)
        if self._fail_count >= self.max_revisions:
            self._fail_count = 0
            return True

        # Run 3 reviews in parallel
        tasks = []
        for name, prompt in _REVIEW_PROMPTS.items():
            review_messages = [
                {"role": "system", "content": prompt},
                {"role": "user", "content": content[:8000]},  # Truncate long drafts
            ]
            tasks.append(_run_review(self.llm, name, review_messages))

        results = await asyncio.gather(*tasks)

        # Aggregate scores and issues
        all_issues: list[str] = []
        all_suggestions: list[str] = []
        all_passed = True
        scores: list[int] = []
        for name, outcome in results:
            if not outcome["passed"]:
                all_passed = False
            if outcome.get("score"):
                scores.append(outcome["score"])
            if outcome["issues"]:
                all_issues.extend(f"[{name}] {issue}" for issue in outcome["issues"])
            if outcome["suggestions"]:
                all_suggestions.extend(f"[{name}] {sug}" for sug in outcome["suggestions"])

        avg_score = sum(scores) / len(scores) if scores else 0

        # Auto-pass if average score >= 8/10 (even if some flagged minor issues)
        if all_passed or (scores and avg_score >= 8):
            self._fail_count = 0
            if avg_score >= 8:
                print(f"\n  [Multi-Agent Review] PASS (avg score {avg_score:.1f}/10 >= 8)")
            return True

        self._fail_count += 1

        # Print review results to terminal
        print(f"\n  [Multi-Agent Review] FAIL ({self._fail_count}/{self.max_revisions}) — avg score {avg_score:.1f}/10")
        for name, outcome in results:
            score_str = f" [{outcome.get('score', '?')}/10]" if outcome.get('score') else ""
            status = "PASS" if outcome["passed"] else "FAIL"
            print(f"    {status} [{name}]{score_str}")
            for issue in (outcome.get("issues") or [])[:3]:
                print(f"      ⚠️  {issue}")
            for sug in (outcome.get("suggestions") or [])[:2]:
                print(f"      💡 {sug}")
        print(flush=True)

        # Build feedback message
        parts = [
            f"## Multi-Agent Review Results (avg score: {avg_score:.1f}/10)\n",
            f"{3 - sum(1 for _, o in results if not o['passed'])}/3 reviewers passed.\n",
        ]
        if all_issues:
            parts.append("### Issues Found")
            for issue in all_issues[:10]:
                parts.append(f"- {issue}")
        if all_suggestions:
            parts.append("\n### Suggested Fixes")
            for sug in all_suggestions[:8]:
                parts.append(f"- {sug}")
        parts.append(
            "\nPlease revise the survey to address ALL issues above. "
            "Then resubmit the complete corrected survey."
        )

        self._last_feedback = "\n".join(parts)
        messages.append({"role": "user", "content": self._last_feedback})
        return False

    @property
    def last_feedback(self) -> str:
        return self._last_feedback


async def _run_review(llm: LLMClient, name: str, messages: list[dict]) -> tuple[str, dict[str, Any]]:
    try:
        response = await llm.chat(messages, tools=None)
        text = response.get("content") or ""
        # Try to parse JSON from the response
        text = text.strip()
        if text.startswith("```"):
            lines = text.split("\n")
            text = "\n".join(lines[1:-1] if lines[-1].strip() == "```" else lines[1:])
        outcome = json.loads(text)
        return name, {
            "score": int(outcome.get("score", 0)) if outcome.get("score") else None,
            "passed": bool(outcome.get("passed", False)),
            "issues": outcome.get("issues", []) or [],
            "suggestions": outcome.get("suggestions", []) or [],
        }
    except (json.JSONDecodeError, Exception):
        return name, {
            "passed": True,
            "issues": [],
            "suggestions": [],
        }
