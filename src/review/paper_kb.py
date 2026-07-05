import re

class PaperKB:
    """Tracks papers discovered via Sciverse during the session.

    Since Sciverse only indexes real papers, any doc_id here maps to
    an actual published paper. Used to verify the References section.
    """

    def __init__(self):
        self._ids: set[str] = set()
        self._titles: dict[str, str] = {}

    _HIT_PAT = re.compile(
        r"\[\d+\] doc_id:\s*(?P<doc_id>[a-f0-9]{10,})\s*\n"
        r"\s*title:\s*(?P<title>.+?)\s*\n"
    )

    _REF_PAT = re.compile(
        r"\[(?P<num>\d+)\]\s+.*?doc_id:\s*(?P<doc_id>[a-f0-9]{10,})",
        re.IGNORECASE,
    )

    def add_from_search_result(self, _tool_args: dict, result_str: str):
        if not result_str.startswith("Found "):
            return
        for m in self._HIT_PAT.finditer(result_str):
            doc_id = m.group("doc_id")
            self._ids.add(doc_id)
            self._titles[doc_id] = m.group("title").strip()

    def mark_read(self, doc_id: str, _offset: int = 0):
        self._ids.add(doc_id)

    def has_doc(self, doc_id: str) -> bool:
        return doc_id in self._ids

    def known_count(self) -> int:
        return len(self._ids)

    def verify_references(self, text: str) -> tuple[int, int, list[str]]:
        """Parse References section, verify each doc_id against KB.

        Returns (total_refs, verified_count, list_of_failure_descriptions).
        Each reference entry in markdown must contain doc_id: <hex>.
        """
        total = 0
        verified = 0
        failures: list[str] = []

        for m in self._REF_PAT.finditer(text):
            total += 1
            num = m.group("num")
            doc_id = m.group("doc_id")
            if self.has_doc(doc_id):
                verified += 1
            else:
                failures.append(f"[{num}] doc_id={doc_id} — not found in session")

        return total, verified, failures

    def list_for_writing(self) -> str:
        """Return a compact index the LLM can use for citations."""
        lines = [f"Papers available for citation ({len(self._ids)} total):"]
        for i, (doc_id, title) in enumerate(
            sorted(self._titles.items()), start=1
        ):
            lines.append(f"  [{i}] {title[:80]}  (doc_id: {doc_id})")
        return "\n".join(lines)
