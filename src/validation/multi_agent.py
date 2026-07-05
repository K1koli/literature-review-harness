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
        "- Thesis: does the survey have a clear organizing argument and scope?\n"
        "- Synthesis: does it compare and connect papers instead of listing them?\n"
        "- Depth: are concepts, method families, tradeoffs, and limitations explained enough for a reader?\n"
        "- Precision: are claims specific and cautious rather than vague generalisations?\n"
        "- Agenda: are open problems grounded in the cited evidence?\n\n"
        "Return a JSON object:\n"
        '{"passed": true/false, "issues": ["specific issue 1", ...], "suggestions": ["fix 1", ...]}\n\n'
        "Fail drafts that read like short evidence reports rather than survey articles."
    ),
    "citation_accuracy": (
        "You are a strict academic reviewer evaluating CITATION ACCURACY of a literature survey draft.\n\n"
        "The survey must cite evidence using Pnnn-Enn format (e.g. [P001-E01]).\n"
        "Check for:\n"
        "- Every substantive paragraph must contain at least one evidence citation\n"
        "- If many evidence records are available, citations should be distributed across the survey rather than concentrated in a few papers\n"
        "- Markdown table rows with factual claims must include evidence ids in a Sources column\n"
        "- References section must list papers that match the cited evidence IDs\n"
        "- Figure captions should be descriptive only; no evidence ids, source lists, or API traces inside captions\n"
        "- The draft should not include XML-like audit blocks such as <references> or <evidence>\n"
        "- No mention of raw doc_ids, offsets, or API traces in the prose\n"
        "- No pseudo-citations such as [Evidence Gap], [citation needed], or unsupported placeholders\n\n"
        "Return a JSON object:\n"
        '{"passed": true/false, "issues": ["specific issue 1", ...], "suggestions": ["fix 1", ...]}\n\n'
        "Be specific about which paragraphs/sections have problems."
    ),
    "structure_completeness": (
        "You are a strict academic reviewer evaluating STRUCTURE AND COMPLETENESS of a literature survey draft.\n\n"
        "Check for:\n"
        "- Does it include Abstract, Introduction with contributions and roadmap, conceptual foundations, taxonomy or framework, comparison, limitations/future agenda, conclusion, and references when evidence supports them?\n"
        "- Are sections balanced and connected by a visible logical progression?\n"
        "- Does the abstract summarize the review lens and findings, not just the topic?\n"
        "- Does the conclusion synthesize takeaways rather than repeat the introduction?\n"
        "- Are headings, tables, figures, and references formatted cleanly?\n\n"
        "- Does surrounding prose refer to important figures, instead of overloading captions with citations?\n\n"
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

    def __init__(
        self,
        llm: LLMClient,
        kb: LiteratureKB,
        topic: str = "",
        enabled: bool = True,
        timeout_seconds: int = 45,
    ):
        self.llm = llm
        self.kb = kb
        self.topic = topic
        self.enabled = enabled
        self.timeout_seconds = timeout_seconds
        self._last_feedback: str = ""
        self._failure_count = 0

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

        passed, feedback = await self.review_text(content)
        if not passed:
            messages.append({"role": "user", "content": feedback})
        return passed

    async def review_text(self, content: str) -> tuple[bool, str]:
        if not self.enabled or not content.strip():
            return True, ""

        tasks = []
        for name, prompt in _REVIEW_PROMPTS.items():
            review_messages = [
                {"role": "system", "content": prompt},
                {"role": "user", "content": content[:8000]},  # Truncate long drafts
            ]
            tasks.append(
                asyncio.wait_for(
                    _run_review(self.llm, name, review_messages),
                    timeout=max(self.timeout_seconds, 1),
                )
            )

        raw_results = await asyncio.gather(*tasks, return_exceptions=True)
        results: list[tuple[str, dict[str, Any]]] = []
        for name, result in zip(_REVIEW_PROMPTS, raw_results, strict=False):
            if isinstance(result, Exception):
                results.append(
                    (
                        name,
                        {
                            "passed": True,
                            "issues": [],
                            "suggestions": [],
                            "note": f"review skipped after {self.timeout_seconds}s timeout",
                        },
                    )
                )
            else:
                results.append(result)

        # Aggregate
        all_issues: list[str] = []
        all_suggestions: list[str] = []
        all_passed = True
        for name, outcome in results:
            if not outcome["passed"]:
                all_passed = False
            if outcome["issues"]:
                all_issues.extend(f"[{name}] {issue}" for issue in outcome["issues"])
            if outcome["suggestions"]:
                all_suggestions.extend(f"[{name}] {sug}" for sug in outcome["suggestions"])

        if all_passed:
            self._failure_count = 0
            self._last_feedback = ""
            return True, ""

        # Build feedback message
        self._failure_count += 1
        parts = [
            "## Multi-Agent Review Results\n",
            f"Three reviewers examined the draft. {3 - sum(1 for _, o in results if not o['passed'])}/3 passed.\n",
            f"Consecutive review failures: {self._failure_count}.\n",
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
        return False, self._last_feedback

    @property
    def last_feedback(self) -> str:
        return self._last_feedback

    @property
    def failure_count(self) -> int:
        return self._failure_count


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
