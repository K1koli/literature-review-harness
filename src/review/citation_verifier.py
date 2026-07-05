import re
from typing import Any

from .paper_kb import PaperKB

_PLACEHOLDER_PATTERNS = [
    re.compile(p, re.IGNORECASE)
    for p in [
        r"Various works (have|on|in)",
        r"Several studies",
        r"Multiple (studies|papers|works|approaches)",
        r"(Some|Certain) studies suggest",
        r"(Recent|Current) work has shown",
        r"A number of (studies|papers)",
    ]
]


class CitationVerifier:
    def check(self, text: str, kb: PaperKB) -> dict[str, Any]:
        total, verified, failures = kb.verify_references(text)
        placeholders = self._find_placeholders(text)
        return {
            "total": total,
            "verified": verified,
            "failures": failures,
            "placeholders": placeholders,
            "passed": len(failures) == 0 and len(placeholders) == 0,
        }

    def _find_placeholders(self, text: str) -> list[str]:
        hits: list[str] = []
        for pat in _PLACEHOLDER_PATTERNS:
            for m in pat.finditer(text):
                snippet = text[max(0, m.start() - 20):m.end() + 40].replace("\n", " ")
                hits.append(snippet[:100])
        return hits


def create_hallucination_guard(kb: PaperKB):
    verifier = CitationVerifier()

    def post_llm_hook(message: dict) -> dict:
        content = message.get("content", "")
        if not content or message.get("tool_calls"):
            return message

        result = verifier.check(content, kb)
        if result["passed"]:
            return message

        parts = [
            "\n\n---",
            "⚠️ **Citation Verification Report**",
            f"  Verified references: {result['verified']}/{result['total']}",
        ]
        if result["failures"]:
            parts.append("  ❌ References with invalid doc_ids (must fix):")
            for item in result["failures"]:
                parts.append(f"    - {item}")
        if result["placeholders"]:
            parts.append("  ❌ Vague placeholder phrases to replace:")
            for p in result["placeholders"]:
                parts.append(f'    - "{p}"')

        parts.append(
            "\nEach [N] reference in the References section must include "
            "a real doc_id from search_literature results. "
            "Remove or replace entries with unverifiable doc_ids."
        )
        message["content"] = content + "\n".join(parts)
        return message

    def stop_condition(messages: list) -> bool:
        last = messages[-1]
        content = last.get("content", "")
        return verifier.check(content, kb)["passed"]

    return post_llm_hook, stop_condition
