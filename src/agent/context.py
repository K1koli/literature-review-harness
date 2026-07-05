from typing import Any, Callable

SYSTEM_PROMPT = """You are a rigorous academic literature review agent. Your task is to produce a high-quality survey on the given topic.

## Efficiency Rules (IMPORTANT)
- Always make MULTIPLE tool calls per iteration (2-5). Never just one.
- Batch read_evidence: request several Pxxx-Exx IDs in one iteration.
- Batch search_literature: search different query angles simultaneously.
- Complete evidence gathering within 5 iterations, then start writing.

## Workflow
1. **Build KB first**: Call `build_literature_kb` for the topic before drafting. It builds a Sciverse evidence KB and opportunistically enriches it with MinerU.
2. **Inspect evidence**: Use `list_evidence`, `read_evidence`, `search_literature`, and `read_context` to gather enough cited evidence.
3. **Write**: After gathering sufficient evidence, write a comprehensive survey grounded only in evidence ids.

## Citation Format (MANDATORY)
- Inline citations: use [1], [2], [3] referring to References entries.
- Before writing References, call `list_evidence` to see all available paper_ids.
- References section: each paper appears EXACTLY ONCE with its paper_id.
  Format: [1] Title. Authors. Year. paper_id: P001
- NEVER reuse the same paper_id under different numbers.
- EVERY paper_id MUST come from list_evidence — never invent.
- NEVER fabricate paper titles, authors, or findings.
- Do NOT use vague placeholders like "Various works on...", "Several studies...", etc.

## Survey Structure
1. Introduction and background
2. Key approaches and methods (categorized)
3. Comparative analysis
4. Future directions and open challenges
5. References (numbered list, each with paper_id)

Output in well-structured Markdown."""


class ContextBuilder:
    """Assembles conversation context for the agent loop.

    Extension points (pre_llm_hooks, post_tool_hooks) allow future modules
    (Skills, Memory, compression) to inject or transform content.
    """

    def __init__(self, system_prompt: str | None = None):
        self.system_prompt = system_prompt or SYSTEM_PROMPT
        self._pre_llm_hooks: list[Callable] = []   # (messages, tools) -> (messages, tools)
        self._post_tool_hooks: list[Callable] = []  # (tool_result: str) -> str

    def add_pre_llm_hook(self, hook: Callable):
        """Add a hook called before each LLM call: hook(messages, tools) -> (messages, tools)."""
        self._pre_llm_hooks.append(hook)

    def add_post_tool_hook(self, hook: Callable):
        """Add a hook to transform tool results: hook(result: str) -> str."""
        self._post_tool_hooks.append(hook)

    def build_initial(self, user_message: str) -> list[dict[str, Any]]:
        """Build the initial message list for a new conversation."""
        return [
            {"role": "system", "content": self.system_prompt},
            {"role": "user", "content": user_message},
        ]

    def apply_pre_llm_hooks(self, messages: list[dict], tools: list[dict]) -> tuple[list[dict], list[dict]]:
        for hook in self._pre_llm_hooks:
            messages, tools = hook(messages, tools)
        return messages, tools

    def apply_post_tool_hooks(self, result: str) -> str:
        for hook in self._post_tool_hooks:
            result = hook(result)
        return result

    def build_tool_result_message(self, tool_call_id: str, result: str) -> dict[str, Any]:
        """Build a tool result message."""
        result = self.apply_post_tool_hooks(result)
        return {
            "role": "tool",
            "tool_call_id": tool_call_id,
            "content": result,
        }
