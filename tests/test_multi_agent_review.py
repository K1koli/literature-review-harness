from __future__ import annotations

import asyncio
import json
import unittest
from typing import Any

from src.state.kb import LiteratureKB
from src.validation.multi_agent import MultiAgentReviewer


class ReviewFakeLLM:
    def __init__(self, outcomes: list[dict[str, Any]]) -> None:
        self.outcomes = outcomes
        self.calls = 0

    async def chat(self, messages, tools=None):
        outcome = self.outcomes[min(self.calls, len(self.outcomes) - 1)]
        self.calls += 1
        return {"content": json.dumps(outcome)}


class MultiAgentReviewTest(unittest.TestCase):
    def test_review_text_runs_three_reviews_and_aggregates_feedback(self) -> None:
        llm = ReviewFakeLLM(
            [
                {"passed": False, "issues": ["weak synthesis"], "suggestions": ["compare methods"]},
                {"passed": True, "issues": [], "suggestions": []},
                {"passed": False, "issues": ["missing future work"], "suggestions": ["add agenda"]},
            ]
        )
        reviewer = MultiAgentReviewer(llm, LiteratureKB(), topic="World Models")

        passed, feedback = asyncio.run(reviewer.review_text("draft " * 2000))

        self.assertFalse(passed)
        self.assertEqual(llm.calls, 3)
        self.assertEqual(reviewer.failure_count, 1)
        self.assertIn("Multi-Agent Review Results", feedback)
        self.assertIn("weak synthesis", feedback)
        self.assertIn("missing future work", feedback)

    def test_review_text_resets_counter_when_all_pass(self) -> None:
        llm = ReviewFakeLLM(
            [
                {"passed": True, "issues": [], "suggestions": []},
                {"passed": True, "issues": [], "suggestions": []},
                {"passed": True, "issues": [], "suggestions": []},
            ]
        )
        reviewer = MultiAgentReviewer(llm, LiteratureKB(), topic="World Models")
        reviewer._failure_count = 2

        passed, feedback = asyncio.run(reviewer.review_text("draft " * 2000))

        self.assertTrue(passed)
        self.assertEqual(feedback, "")
        self.assertEqual(reviewer.failure_count, 0)


if __name__ == "__main__":
    unittest.main()
