from __future__ import annotations

import asyncio
import json
import unittest
from typing import Any

from src.agent.context import ContextBuilder
from src.agent.loop import AgentLoop
from src.tools.registry import ToolRegistry


class DummyLLM:
    def __init__(self) -> None:
        self.calls = 0

    async def chat(self, messages: list[dict[str, Any]], tools: list[dict[str, Any]]) -> dict[str, Any]:
        self.calls += 1
        if self.calls == 1:
            return {
                "role": "assistant",
                "tool_calls": [
                    {
                        "id": "call_1",
                        "function": {"name": "dummy_tool", "arguments": '{"value": 3}'},
                    }
                ],
            }
        return {"role": "assistant", "content": "Final answer with P001-E01."}

    @staticmethod
    def has_tool_calls(message: dict[str, Any]) -> bool:
        return bool(message.get("tool_calls"))

    @staticmethod
    def has_content(message: dict[str, Any]) -> bool:
        return bool(message.get("content"))

    @staticmethod
    def extract_tool_calls(message: dict[str, Any]) -> list[dict[str, Any]]:
        return [{"id": "call_1", "name": "dummy_tool", "arguments": {"value": 3}}]


class DummyTool:
    name = "dummy_tool"
    description = "A deterministic dummy tool."
    parameters = {"type": "object", "properties": {"value": {"type": "integer"}}}

    async def execute(self, value: int) -> str:
        return f"value={value}"


class ParallelDummyLLM:
    def __init__(self) -> None:
        self.calls = 0

    async def chat(self, messages: list[dict[str, Any]], tools: list[dict[str, Any]]) -> dict[str, Any]:
        self.calls += 1
        if self.calls == 1:
            return {
                "role": "assistant",
                "tool_calls": [
                    {
                        "id": "call_1",
                        "function": {"name": "dummy_tool", "arguments": '{"value": 1}'},
                    },
                    {
                        "id": "call_2",
                        "function": {"name": "dummy_tool", "arguments": '{"value": 2}'},
                    },
                ],
            }
        return {"role": "assistant", "content": "Final answer with P001-E01."}

    @staticmethod
    def has_tool_calls(message: dict[str, Any]) -> bool:
        return bool(message.get("tool_calls"))

    @staticmethod
    def has_content(message: dict[str, Any]) -> bool:
        return bool(message.get("content"))

    @staticmethod
    def extract_tool_calls(message: dict[str, Any]) -> list[dict[str, Any]]:
        calls = []
        for tc in message.get("tool_calls", []):
            calls.append(
                {
                    "id": tc["id"],
                    "name": tc["function"]["name"],
                    "arguments": json.loads(tc["function"]["arguments"]),
                }
            )
        return calls


class PassingCondition:
    def __call__(self, messages: list[dict[str, Any]]) -> bool:
        return True

    def report_dict(self) -> dict[str, Any]:
        return {"status": "pass"}


class AsyncPassingCondition:
    async def __call__(self, messages: list[dict[str, Any]]) -> bool:
        await asyncio.sleep(0)
        return True


class AgentLoopEventsTest(unittest.TestCase):
    def test_emits_structured_events_for_tool_and_stop_condition(self) -> None:
        registry = ToolRegistry()
        registry.register(DummyTool())
        events: list[dict[str, Any]] = []
        loop = AgentLoop(
            llm=DummyLLM(),
            registry=registry,
            context=ContextBuilder(system_prompt="test"),
            max_iterations=3,
            verbose=False,
            event_sink=events.append,
        )
        loop.add_stop_condition(PassingCondition())

        result = asyncio.run(loop.run("Do the task."))

        self.assertEqual(result, "Final answer with P001-E01.")
        event_types = [event["type"] for event in events]
        self.assertIn("run_started", event_types)
        self.assertIn("tool_call_started", event_types)
        self.assertIn("tool_call_finished", event_types)
        self.assertIn("stop_condition", event_types)
        self.assertIn("run_completed", event_types)
        tool_event = next(event for event in events if event["type"] == "tool_call_finished")
        self.assertEqual(tool_event["name"], "dummy_tool")
        self.assertEqual(tool_event["result_preview"], "value=3")

    def test_emits_events_for_parallel_tools_and_async_stop_condition(self) -> None:
        registry = ToolRegistry()
        registry.register(DummyTool())
        events: list[dict[str, Any]] = []
        loop = AgentLoop(
            llm=ParallelDummyLLM(),
            registry=registry,
            context=ContextBuilder(system_prompt="test"),
            max_iterations=3,
            verbose=False,
            event_sink=events.append,
        )
        loop.add_stop_condition(AsyncPassingCondition())

        result = asyncio.run(loop.run("Do the task."))

        self.assertEqual(result, "Final answer with P001-E01.")
        started = [event for event in events if event["type"] == "tool_call_started"]
        finished = [event for event in events if event["type"] == "tool_call_finished"]
        self.assertEqual([event["name"] for event in started], ["dummy_tool", "dummy_tool"])
        self.assertEqual([event["result_preview"] for event in finished], ["value=1", "value=2"])
        stop_event = next(event for event in events if event["type"] == "stop_condition")
        self.assertTrue(stop_event["passed"])


if __name__ == "__main__":
    unittest.main()
