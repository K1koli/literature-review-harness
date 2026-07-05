from __future__ import annotations

import asyncio
import unittest

from src.agent.context import ContextBuilder
from src.agent.loop import AgentLoop
from src.tools.registry import ToolRegistry


class DraftOnlyLLM:
    def __init__(self) -> None:
        self.calls = 0

    async def chat(self, messages, tools=None):
        self.calls += 1
        return {"role": "assistant", "content": f"Draft version {self.calls} [P001-E01]."}

    @staticmethod
    def has_tool_calls(message):
        return False

    @staticmethod
    def has_content(message):
        return bool(message.get("content"))


class AlwaysFailStopCondition:
    def __init__(self) -> None:
        self.calls = 0

    def __call__(self, messages):
        self.calls += 1
        messages.append({"role": "user", "content": "review feedback"})
        return False


class AgentLoopTest(unittest.TestCase):
    def test_revision_budget_returns_latest_draft(self) -> None:
        llm = DraftOnlyLLM()
        stop = AlwaysFailStopCondition()
        loop = AgentLoop(
            llm=llm,
            registry=ToolRegistry(),
            context=ContextBuilder(system_prompt="test"),
            max_iterations=20,
            max_revision_rounds=3,
            verbose=False,
        )
        loop.add_stop_condition(stop)

        result = asyncio.run(loop.run("write"))

        self.assertEqual(result, "Draft version 4 [P001-E01].")
        self.assertEqual(llm.calls, 4)
        self.assertEqual(stop.calls, 4)


if __name__ == "__main__":
    unittest.main()
