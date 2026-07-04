import json
import httpx
from typing import Any


class LLMClient:
    """OpenAI-compatible LLM client for Intern-S2-Preview API."""

    def __init__(self, api_base: str, api_key: str, model: str = "intern-s2-preview"):
        self.api_base = api_base.rstrip("/")
        self.api_key = api_key
        self.model = model
        self._client = httpx.AsyncClient(timeout=httpx.Timeout(120.0))

    async def chat(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        """Send a chat completion request. Returns the response message dict."""
        body: dict[str, Any] = {
            "model": self.model,
            "messages": messages,
        }
        if tools:
            body["tools"] = tools
            body["tool_choice"] = "auto"

        response = await self._client.post(
            f"{self.api_base}/chat/completions",
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            },
            json=body,
        )
        response.raise_for_status()
        data = response.json()
        choice = data["choices"][0]
        return choice["message"]

    async def close(self):
        await self._client.aclose()

    @staticmethod
    def has_tool_calls(message: dict[str, Any]) -> bool:
        return bool(message.get("tool_calls"))

    @staticmethod
    def has_content(message: dict[str, Any]) -> bool:
        return bool(message.get("content"))

    @staticmethod
    def extract_tool_calls(message: dict[str, Any]) -> list[dict[str, Any]]:
        """Extract tool calls from message, parsing JSON arguments."""
        result = []
        for tc in message.get("tool_calls", []):
            func = tc["function"]
            try:
                args = json.loads(func["arguments"])
            except (json.JSONDecodeError, KeyError):
                args = {}
            result.append({
                "id": tc.get("id", ""),
                "name": func["name"],
                "arguments": args,
            })
        return result
