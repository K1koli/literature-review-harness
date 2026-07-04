import json
import sys
from datetime import UTC, datetime
from typing import Any, Callable

from ..llm.client import LLMClient
from ..tools.registry import ToolRegistry
from .context import ContextBuilder


class AgentLoop:
    """Core agent loop: context → LLM → tool calls → execute → loop → final output.

    Extension points:
    - add_post_llm_hook(hook): hook(message) -> message (for hallucination check, etc.)
    - add_stop_condition(cond): cond(messages) -> bool (for quality-based stopping)
    - sub_loops: spawn another AgentLoop for parallel sub-agent review
    """

    def __init__(
        self,
        llm: LLMClient,
        registry: ToolRegistry,
        context: ContextBuilder,
        max_iterations: int = 15,
        verbose: bool = True,
        event_sink: Callable[[dict[str, Any]], None] | None = None,
    ):
        self.llm = llm
        self.registry = registry
        self.context = context
        self.max_iterations = max_iterations
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

        for iteration in range(1, self.max_iterations + 1):
            self._log(f"\n--- Iteration {iteration}/{self.max_iterations} ---")
            self._emit("iteration_started", iteration=iteration, max_iterations=self.max_iterations)

            # Apply pre-LLM hooks (Skills, Memory injection)
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
                self._log(f"LLM requested {len(tool_calls)} tool call(s)")
                self._emit(
                    "llm_response",
                    iteration=iteration,
                    mode="tool_calls",
                    tool_call_count=len(tool_calls),
                    tool_names=[tc["name"] for tc in tool_calls],
                )

                for idx, tc in enumerate(tool_calls, 1):
                    self._emit(
                        "tool_call_started",
                        iteration=iteration,
                        index=idx,
                        total=len(tool_calls),
                        name=tc["name"],
                        arguments=tc["arguments"],
                    )
                    result = await self.registry.execute(tc["name"], tc["arguments"])
                    self._log_tool_call(tc["name"], tc["arguments"], result, idx, len(tool_calls))
                    self._emit(
                        "tool_call_finished",
                        iteration=iteration,
                        index=idx,
                        total=len(tool_calls),
                        name=tc["name"],
                        result_preview=result[:800],
                        result_chars=len(result),
                    )
                    messages.append(
                        self.context.build_tool_result_message(tc["id"], result)
                    )
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

                # Check stop conditions
                all_stop = True
                for cond in self._stop_conditions:
                    passed = cond(messages)
                    report = cond.report_dict() if hasattr(cond, "report_dict") else None
                    self._emit(
                        "stop_condition",
                        iteration=iteration,
                        name=cond.__class__.__name__,
                        passed=passed,
                        report=report,
                    )
                    if not passed:
                        all_stop = False
                        self._log(f"Stop condition not met, continuing...")
                        break

                if all_stop:
                    self._log("=" * 60)
                    self._log("Task complete.")
                    self._emit("run_completed", iterations=iteration, content_chars=len(content))
                    return content
                else:
                    # Not all conditions met, but LLM stopped calling tools.
                    # Ask LLM to continue improving.
                    messages.append({
                        "role": "user",
                        "content": "Please continue improving the survey based on the review feedback above."
                    })
                    continue

            # Neither tool calls nor content - unexpected
            self._log("LLM returned neither tool_calls nor content. Stopping.")
            self._emit("run_stopped_unexpectedly", iteration=iteration)
            break

        self._emit("run_max_iterations", max_iterations=self.max_iterations)
        return "Agent loop reached maximum iterations without completing the task."
