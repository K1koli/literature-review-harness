import asyncio
import json
import sys
from datetime import UTC, datetime
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
        event_sink: Callable[[dict[str, Any]], None] | None = None,
    ):
        self.llm = llm
        self.registry = registry
        self.context = context
        self.max_iterations = max_iterations
        self.max_revision_rounds = max(0, max_revision_rounds)
        self.max_tool_calls_per_iteration = max(1, max_tool_calls_per_iteration)
        self.verbose = verbose
        self.event_sink = event_sink
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

    def _emit(self, event_type: str, **payload: Any) -> None:
        if self.event_sink is None:
            return
        event = {
            "type": event_type,
            "ts": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
            **payload,
        }
        try:
            self.event_sink(event)
        except Exception as exc:
            if self.verbose:
                print(f"\nEvent sink failed: {exc}", file=sys.stderr, flush=True)

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
        self._emit(
            "run_started",
            task_preview=user_message[:240],
            available_tools=self.registry.list_names(),
            max_iterations=self.max_iterations,
        )

        revision_requests = 0
        for iteration in range(1, self.max_iterations + 1):
            self._log(f"\n--- Iteration {iteration}/{self.max_iterations} ---")
            self._emit("iteration_started", iteration=iteration, max_iterations=self.max_iterations)

            # Apply pre-LLM hooks such as context injection or tool filtering.
            msgs, tools = self.context.apply_pre_llm_hooks(messages, tools_schema)
            self._emit(
                "context_prepared",
                iteration=iteration,
                message_count=len(msgs),
                tool_count=len(tools),
            )

            # Call LLM
            self._log("Calling LLM...")
            self._emit("llm_call_started", iteration=iteration)
            try:
                response = await self.llm.chat(msgs, tools)
            except Exception as e:
                self._log(f"LLM call failed: {e}")
                self._emit("llm_call_failed", iteration=iteration, error=str(e))
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
                    self._emit(
                        "tool_calls_capped",
                        iteration=iteration,
                        requested=len(tool_calls),
                        executed=self.max_tool_calls_per_iteration,
                    )
                    tool_calls = tool_calls[: self.max_tool_calls_per_iteration]
                self._log(f"LLM requested {len(tool_calls)} tool call(s)")
                self._emit(
                    "llm_response",
                    iteration=iteration,
                    mode="tool_calls",
                    tool_call_count=len(tool_calls),
                    tool_names=[tc["name"] for tc in tool_calls],
                )

                if len(tool_calls) > 1:
                    async def _exec(idx: int, tc: dict[str, Any]):
                        self._emit(
                            "tool_call_started",
                            iteration=iteration,
                            index=idx,
                            total=len(tool_calls),
                            name=tc["name"],
                            arguments=tc["arguments"],
                        )
                        result = await self.registry.execute(tc["name"], tc["arguments"])
                        self._emit(
                            "tool_call_finished",
                            iteration=iteration,
                            index=idx,
                            total=len(tool_calls),
                            name=tc["name"],
                            result_preview=result[:800],
                            result_chars=len(result),
                        )
                        return tc["id"], tc["name"], tc["arguments"], result
                    results = await asyncio.gather(
                        *[_exec(idx, tc) for idx, tc in enumerate(tool_calls, 1)]
                    )
                    for idx, (tc_id, name, args, result) in enumerate(results, 1):
                        self._log_tool_call(name, args, result, idx, len(results))
                        messages.append(self.context.build_tool_result_message(tc_id, result))
                else:
                    tc = tool_calls[0]
                    self._emit(
                        "tool_call_started",
                        iteration=iteration,
                        index=1,
                        total=1,
                        name=tc["name"],
                        arguments=tc["arguments"],
                    )
                    result = await self.registry.execute(tc["name"], tc["arguments"])
                    self._emit(
                        "tool_call_finished",
                        iteration=iteration,
                        index=1,
                        total=1,
                        name=tc["name"],
                        result_preview=result[:800],
                        result_chars=len(result),
                    )
                    self._log_tool_call(tc["name"], tc["arguments"], result, 1, 1)
                    messages.append(self.context.build_tool_result_message(tc["id"], result))
                continue

            # No tool calls - LLM is producing final content
            if self.llm.has_content(response):
                content = response.get("content", "")
                self._log(f"LLM final response ({len(content)} chars)")
                self._emit(
                    "llm_response",
                    iteration=iteration,
                    mode="final_content",
                    content_chars=len(content),
                )

                # Check stop conditions (supports sync and async)
                all_stop = True
                for cond in self._stop_conditions:
                    result = cond(messages)
                    if asyncio.iscoroutine(result):
                        result = await result
                    report = cond.report_dict() if hasattr(cond, "report_dict") else None
                    self._emit(
                        "stop_condition",
                        iteration=iteration,
                        name=cond.__class__.__name__,
                        passed=bool(result),
                        report=report,
                    )
                    if not result:
                        all_stop = False
                        self._log(f"Stop condition not met, continuing...")
                        break

                if all_stop:
                    self._log("=" * 60)
                    self._log("Task complete.")
                    self._emit("run_completed", iterations=iteration, content_chars=len(content))
                    return content
                else:
                    if revision_requests >= self.max_revision_rounds:
                        self._log("=" * 60)
                        self._log(
                            "Revision budget exhausted; returning latest draft with audit feedback still available."
                        )
                        self._emit(
                            "revision_budget_exhausted",
                            iterations=iteration,
                            revision_requests=revision_requests,
                            content_chars=len(content),
                        )
                        return content
                    revision_requests += 1
                    self._emit(
                        "revision_requested",
                        iteration=iteration,
                        revision_round=revision_requests,
                        max_revision_rounds=self.max_revision_rounds,
                    )
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
            self._emit("run_stopped_unexpectedly", iteration=iteration)
            break

        self._emit("run_max_iterations", max_iterations=self.max_iterations)
        return "Agent loop reached maximum iterations without completing the task."
