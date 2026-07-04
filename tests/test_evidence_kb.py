import asyncio
import io
import unittest
import zipfile
from unittest.mock import patch

from src.state.kb import LiteratureKB
from src.tools.mineru import MinerUConfig, mineru_evidence_chunks, run_mineru_for_kb
from src.validation.citations import CitationVerifier


class EvidenceKBTest(unittest.TestCase):
    def test_upsert_merges_by_stable_keys_and_assigns_evidence_ids(self) -> None:
        kb = LiteratureKB()
        first = kb.upsert_paper(title="World Models", doc_id="doc-1")
        second = kb.upsert_paper(title="World Models", doi="10.48550/arxiv.1803.10122")

        self.assertIs(first, second)
        self.assertEqual(first.paper_id, "P001")

        evidence = kb.add_evidence(
            first,
            text="World models learn compact latent dynamics that can support planning and imagination.",
            source="sciverse_semantic",
            doc_id="doc-1",
            offset=10,
        )

        self.assertIsNotNone(evidence)
        self.assertEqual(evidence.evidence_id, "P001-E01")
        self.assertEqual(kb.find_by_doc_id("doc-1"), first)

    def test_keep_first_papers_rebuilds_indexes(self) -> None:
        kb = LiteratureKB()
        first = kb.upsert_paper(title="A", doc_id="doc-a")
        second = kb.upsert_paper(title="B", doc_id="doc-b")
        kb.add_evidence(first, text=" ".join(["alpha"] * 30), source="sciverse_semantic")
        kb.add_evidence(second, text=" ".join(["beta"] * 30), source="sciverse_semantic")

        kb.keep_first_papers(1)

        self.assertEqual([paper.paper_id for paper in kb.papers], ["P001"])
        self.assertIsNone(kb.find_by_doc_id("doc-b"))
        self.assertEqual(kb.find_by_doc_id("doc-a"), first)
        self.assertEqual([item.paper_id for item in kb.evidence], ["P001"])


class MinerUTest(unittest.TestCase):
    def test_structured_content_becomes_evidence_chunks(self) -> None:
        structured = {
            "content_list": [
                {"type": "text", "text": "1 Introduction"},
                {"type": "text", "text": " ".join(["latent dynamics"] * 70)},
                {"type": "text", "text": "References"},
                {"type": "text", "text": "This should not be included."},
            ]
        }

        chunks = mineru_evidence_chunks(structured, max_items=2)

        self.assertEqual(len(chunks), 1)
        self.assertIn("latent dynamics", chunks[0])
        self.assertNotIn("This should not be included", chunks[0])

    def test_timeout_marks_unfinished_mineru_tasks_as_skipped(self) -> None:
        class FakeMinerUClient:
            def __init__(self, token: str) -> None:
                self.token = token

            async def submit_url_batch(self, files, *, config, model_version):
                return {"data": {"batch_id": "batch-1"}}

            async def get_batch_result(self, batch_id: str):
                return {"data": {"extract_result": [{"data_id": "P001", "state": "running"}]}}

            async def download_zip(self, url: str):
                raise AssertionError("download should not be called for unfinished task")

        kb = LiteratureKB()
        paper = kb.upsert_paper(title="World Models", parse_url="https://arxiv.org/pdf/1803.10122.pdf")
        kb.add_evidence(paper, text=" ".join(["sciverse"] * 40), source="sciverse_semantic")

        config = MinerUConfig(api_token="token", timeout_seconds=0, poll_interval_seconds=0, batch_size=1)
        with patch("src.tools.mineru.MinerUClient", FakeMinerUClient):
            report = asyncio.run(run_mineru_for_kb(kb, config))

        self.assertEqual(report["skipped"], 1)
        self.assertEqual(paper.mineru["state"], "skipped")
        self.assertEqual(paper.mineru["reason"], "MinerU timeout; using Sciverse evidence")
        self.assertEqual(len(kb.evidence), 1)

    def test_completed_mineru_full_markdown_becomes_structured_evidence(self) -> None:
        class FakeMinerUClient:
            def __init__(self, token: str) -> None:
                self.token = token

            async def submit_url_batch(self, files, *, config, model_version):
                return {"data": {"batch_id": "batch-1"}}

            async def get_batch_result(self, batch_id: str):
                return {
                    "data": {
                        "extract_result": [
                            {"data_id": "P001", "state": "done", "full_zip_url": "https://example.test/result.zip"}
                        ]
                    }
                }

            async def download_zip(self, url: str):
                buffer = io.BytesIO()
                with zipfile.ZipFile(buffer, "w") as archive:
                    archive.writestr("paper/full.md", "Introduction\n\n" + " ".join(["world model"] * 80))
                return buffer.getvalue()

        kb = LiteratureKB()
        paper = kb.upsert_paper(title="World Models", parse_url="https://arxiv.org/pdf/1803.10122.pdf")

        config = MinerUConfig(api_token="token", timeout_seconds=1, poll_interval_seconds=0, batch_size=1)
        with patch("src.tools.mineru.MinerUClient", FakeMinerUClient):
            report = asyncio.run(run_mineru_for_kb(kb, config))

        self.assertEqual(report["done"], 1)
        self.assertEqual(paper.mineru["state"], "done")
        self.assertTrue(paper.mineru["structured_ingested"])
        self.assertEqual(kb.evidence[0].source, "mineru_structured")
        self.assertIn("world model", kb.evidence[0].text)


class CitationVerifierTest(unittest.TestCase):
    def test_rejects_unknown_evidence_ids(self) -> None:
        kb = LiteratureKB()
        report = CitationVerifier(kb).validate_text(
            "# Survey\n\nThis paragraph cites an evidence id that is not present in the KB [P999-E01]."
        )

        self.assertEqual(report.status, "fail")
        self.assertEqual(report.errors[0]["issue"], "unknown_evidence_id")

    def test_accepts_known_evidence_ids_and_flags_missing_paragraph_citations(self) -> None:
        kb = LiteratureKB()
        paper = kb.upsert_paper(title="World Models")
        evidence = kb.add_evidence(paper, text=" ".join(["world"] * 40), source="sciverse_semantic")
        assert evidence is not None

        verifier = CitationVerifier(kb)
        passing = verifier.validate_text(
            "# Survey\n\n"
            f"World-model surveys can discuss latent dynamics when the statement is backed by evidence {evidence.evidence_id}; "
            "this paragraph is deliberately long enough to require citation checking."
        )
        failing = verifier.validate_text(
            "# Survey\n\n"
            "This is a long substantive paragraph without any evidence identifier, so the verifier should reject it "
            "instead of allowing unsupported survey prose into the final answer."
        )

        self.assertEqual(passing.status, "pass")
        self.assertEqual(failing.status, "fail")
        self.assertEqual(failing.errors[0]["issue"], "missing_evidence_citation")


if __name__ == "__main__":
    unittest.main()
