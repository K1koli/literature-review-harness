from typing import Any, Protocol, Callable


class Tool(Protocol):
    """Protocol for tools. Any object satisfying this interface can be registered."""

    name: str
    description: str
    parameters: dict[str, Any]  # JSON Schema

    async def execute(self, **kwargs: Any) -> str: ...


class ToolRegistry:
    """Extensible tool registry.

    Supports decorator and manual registration.
    Exports tools as OpenAI function-calling schema.

    Extension point: override _wrap_execute() to add sandbox behavior.
    """

    def __init__(self):
        self._tools: dict[str, Tool] = {}
        self._hooks: list[Callable] = []  # post_execute hooks

    def register(self, tool: Tool) -> Tool:
        self._tools[tool.name] = tool
        return tool

    def get(self, name: str) -> Tool | None:
        return self._tools.get(name)

    def list_names(self) -> list[str]:
        return list(self._tools.keys())

    def add_hook(self, hook: Callable):
        """Add a post-execute hook: hook(tool_name, args, result) -> result."""
        self._hooks.append(hook)

    async def execute(self, name: str, arguments: dict[str, Any]) -> str:
        tool = self._tools.get(name)
        if tool is None:
            return f"Error: tool '{name}' not found. Available: {self.list_names()}"

        try:
            result = await tool.execute(**arguments)
        except Exception as e:
            result = f"Error executing tool '{name}': {e}"

        for hook in self._hooks:
            result = hook(name, arguments, result)

        return result

    def export_schemas(self) -> list[dict[str, Any]]:
        """Export tools as OpenAI function-calling format."""
        schemas = []
        for tool in self._tools.values():
            schemas.append({
                "type": "function",
                "function": {
                    "name": tool.name,
                    "description": tool.description,
                    "parameters": tool.parameters,
                },
            })
        return schemas
