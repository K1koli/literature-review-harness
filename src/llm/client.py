import json
import httpx
from typing import Any


class LLMRequestError(RuntimeError):
    """Raised when the upstream OpenAI-compatible LLM request cannot complete."""


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

        try:
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
        except httpx.HTTPStatusError as exc:
            body_preview = exc.response.text[:800].replace("\n", " ")
            raise LLMRequestError(
                f"HTTP {exc.response.status_code} from LLM API: {body_preview}"
            ) from exc
        except httpx.TimeoutException as exc:
            raise LLMRequestError(f"{exc.__class__.__name__}: request timed out") from exc
        except httpx.HTTPError as exc:
            error = str(exc) or exc.__class__.__name__
            raise LLMRequestError(f"{exc.__class__.__name__}: {error}") from exc
        except (KeyError, IndexError, json.JSONDecodeError) as exc:
            raise LLMRequestError(f"Malformed LLM response: {exc.__class__.__name__}: {exc}") from exc

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
