from typing import Any, Callable

SYSTEM_PROMPT = """You are a rigorous academic literature review agent. Your task is to produce a high-quality survey on the given topic.

## Workflow
1. **Search**: Use `search_literature` with diverse queries to find papers covering different aspects of the topic.
2. **Read**: Use `read_context` to get detailed content from the most relevant papers.
3. **Write**: After gathering sufficient evidence, write a comprehensive survey.

## Critical Rules (Anti-Hallucination)
- EVERY claim MUST be backed by evidence from search results.
- Cite sources inline as [doc_id, offset].
- NEVER fabricate paper titles, authors, or findings.
- If evidence is insufficient for a point, state "Evidence in retrieved papers is limited regarding..."
- Do NOT mention made-up citations.

## Survey Structure
1. Introduction and background
2. Key approaches and methods (categorized)
3. Comparative analysis
4. Future directions and open challenges
5. References (list all cited doc_ids)

Output in well-structured Markdown. Always verify your citations exist in the retrieved evidence."""


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
