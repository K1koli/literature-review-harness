import httpx

SCIVERSE_BASE = "https://api.sciverse.space"


class SearchLiteratureTool:
    """Semantic literature search via Sciverse agentic-search API."""

    name = "search_literature"
    description = (
        "Search for academic papers using semantic search. "
        "Provide a natural language query describing your research question. "
        "Returns a list of relevant paper snippets with doc_id, title, chunk text, "
        "and relevance score. Use diverse queries to cover different aspects of a topic."
    )
    parameters = {
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": "A natural language research question or keywords to search for papers.",
            },
            "top_k": {
                "type": "integer",
                "description": "Number of results to return (1-100, default 20).",
                "default": 20,
            },
        },
        "required": ["query"],
    }

    def __init__(self, api_token: str):
        self._headers = {"Authorization": f"Bearer {api_token}"}

    async def execute(self, query: str, top_k: int = 10) -> str:
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(
                f"{SCIVERSE_BASE}/agentic-search",
                headers=self._headers,
                json={"query": query, "top_k": top_k},
            )
            resp.raise_for_status()
            hits = resp.json().get("hits") or []

        if not hits:
            return "No results found for this query."

        lines = [f"Found {len(hits)} results for query: '{query}'\n"]
        for i, hit in enumerate(hits):
            lines.append(
                f"[{i}] doc_id: {hit.get('doc_id', 'N/A')}\n"
                f"    title: {hit.get('title', 'N/A')}\n"
                f"    score: {hit.get('score', 0):.4f}\n"
                f"    offset: {hit.get('offset', 0)}\n"
                f"    snippet: {hit.get('chunk', '')[:300]}..."
            )
        return "\n".join(lines)


class ReadContextTool:
    """Read full context of a paper via Sciverse content API."""

    name = "read_context"
    description = (
        "Read the full text context of a paper at a specific offset position. "
        "Use this after search_literature to get detailed content from a paper. "
        "You can call this multiple times with increasing offsets to read more of the paper."
    )
    parameters = {
        "type": "object",
        "properties": {
            "doc_id": {
                "type": "string",
                "description": "The document ID from search_literature results.",
            },
            "offset": {
                "type": "integer",
                "description": "Character offset position to start reading from (default 0).",
                "default": 0,
            },
            "limit": {
                "type": "integer",
                "description": "Number of characters to read (max 4096, default 2000).",
                "default": 2000,
            },
        },
        "required": ["doc_id"],
    }

    def __init__(self, api_token: str):
        self._headers = {"Authorization": f"Bearer {api_token}"}

    async def execute(self, doc_id: str, offset: int = 0, limit: int = 2000) -> str:
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.get(
                f"{SCIVERSE_BASE}/content",
                headers=self._headers,
                params={"doc_id": doc_id, "offset": offset, "limit": limit},
            )
            resp.raise_for_status()
            data = resp.json()

        text = data.get("text", "")
        next_offset = data.get("next_offset")
        more = data.get("more", False)

        parts = [
            f"--- Context for {doc_id} (offset={offset}, limit={limit}) ---",
            text,
        ]
        if more:
            parts.append(
                f"\n[More content available. Next offset: {next_offset}. "
                f"Call read_context with offset={next_offset} to continue.]"
            )
        return "\n".join(parts)
