import asyncio
import json
from typing import Any, Callable

from ..llm.client import LLMClient
from ..tools.registry import ToolRegistry
from .context import ContextBuilder


class AgentLoop:
    """Core agent loop: context → LLM → tool calls → execute (parallel) → loop → final output.

    Extension points:
    - add_post_llm_hook(hook): hook(message) -> message (for hallucination check, etc.)
    - add_stop_condition(cond): cond(messages) -> bool | awaitable (for quality-based stopping)
    """

    def __init__(
        self,
        llm: LLMClient,
        registry: ToolRegistry,
        context: ContextBuilder,
        max_iterations: int = 15,
        max_revision_rounds: int = 3,
        max_tool_calls_per_iteration: int = 5,
        verbose: bool = True,
    ):
        self.llm = llm
        self.registry = registry
        self.context = context
        self.max_iterations = max_iterations
        self.max_revision_rounds = max(0, max_revision_rounds)
        self.max_tool_calls_per_iteration = max(1, max_tool_calls_per_iteration)
        self.verbose = verbose
        self._post_llm_hooks: list[Callable] = []
        self._stop_conditions: list[Callable] = []

    def add_post_llm_hook(self, hook: Callable):
        """Add a hook called after each LLM response: hook(message) -> message."""
        self._post_llm_hooks.append(hook)

    def add_stop_condition(self, condition: Callable):
        """Add a stop condition: condition(messages) -> bool."""
        self._stop_conditions.append(condition)

    def _log(self, msg: str):
        if self.verbose:
            print(f"\n{msg}", flush=True)

    def _log_tool_call(self, name: str, args: dict, result: str, idx: int, total: int):
        if self.verbose:
            preview = result[:500].replace("\n", "\n    ")
            print(f"\n  [{idx}/{total}] Tool: {name}({json.dumps(args, ensure_ascii=False)[:200]})", flush=True)
            print(f"    Result: {preview}{'...(truncated)' if len(result) > 500 else ''}", flush=True)

    async def run(self, user_message: str) -> str:
        """Run the agent loop and return the final response text."""
        tools_schema = self.registry.export_schemas()
        messages = self.context.build_initial(user_message)

        self._log("=" * 60)
        self._log(f"Task: {user_message[:100]}...")
        self._log(f"Available tools: {self.registry.list_names()}")
        self._log("=" * 60)

        revision_requests = 0
        for iteration in range(1, self.max_iterations + 1):
            self._log(f"\n--- Iteration {iteration}/{self.max_iterations} ---")

            # Apply pre-LLM hooks such as context injection or tool filtering.
            msgs, tools = self.context.apply_pre_llm_hooks(messages, tools_schema)

            # Call LLM
            self._log("Calling LLM...")
            try:
                response = await self.llm.chat(msgs, tools)
            except Exception as e:
                self._log(f"LLM call failed: {e}")
                return f"Error calling LLM: {e}"

            # Apply post-LLM hooks (hallucination check)
            for hook in self._post_llm_hooks:
                response = hook(response)

            # Append assistant response to message history
            messages.append(response)

            # Check for tool calls
            if self.llm.has_tool_calls(response):
                tool_calls = self.llm.extract_tool_calls(response)
                if len(tool_calls) > self.max_tool_calls_per_iteration:
                    self._log(
                        f"LLM requested {len(tool_calls)} tool calls; executing first "
                        f"{self.max_tool_calls_per_iteration} to control context growth."
                    )
                    tool_calls = tool_calls[: self.max_tool_calls_per_iteration]
                self._log(f"LLM requested {len(tool_calls)} tool call(s)")

                if len(tool_calls) > 1:
                    async def _exec(tc):
                        return tc["id"], tc["name"], tc["arguments"], await self.registry.execute(tc["name"], tc["arguments"])
                    results = await asyncio.gather(*[_exec(tc) for tc in tool_calls])
                    for idx, (tc_id, name, args, result) in enumerate(results, 1):
                        self._log_tool_call(name, args, result, idx, len(results))
                        messages.append(self.context.build_tool_result_message(tc_id, result))
                else:
                    tc = tool_calls[0]
                    result = await self.registry.execute(tc["name"], tc["arguments"])
                    self._log_tool_call(tc["name"], tc["arguments"], result, 1, 1)
                    messages.append(self.context.build_tool_result_message(tc["id"], result))
                continue

            # No tool calls - LLM is producing final content
            if self.llm.has_content(response):
                content = response.get("content", "")
                self._log(f"LLM final response ({len(content)} chars)")

                # Check stop conditions (supports sync and async)
                all_stop = True
                for cond in self._stop_conditions:
                    result = cond(messages)
                    if asyncio.iscoroutine(result):
                        result = await result
                    if not result:
                        all_stop = False
                        self._log(f"Stop condition not met, continuing...")
                        break

                if all_stop:
                    self._log("=" * 60)
                    self._log("Task complete.")
                    return content
                else:
                    if revision_requests >= self.max_revision_rounds:
                        self._log("=" * 60)
                        self._log(
                            "Revision budget exhausted; returning latest draft with audit feedback still available."
                        )
                        return content
                    revision_requests += 1
                    # Not all conditions met, but LLM stopped calling tools.
                    # Ask LLM to continue improving.
                    messages.append({
                        "role": "user",
                        "content": (
                            "Please revise the survey based only on the review feedback above. "
                            "Do not make it longer unless needed; focus on fixing the cited issues, "
                            "citation coverage, and structure. "
                            f"Revision round {revision_requests}/{self.max_revision_rounds}."
                        )
                    })
                    continue

            # Neither tool calls nor content - unexpected
            self._log("LLM returned neither tool_calls nor content. Stopping.")
            break

        return "Agent loop reached maximum iterations without completing the task."
