import asyncio
import io
import json
import unittest
import zipfile
from unittest.mock import patch

from src.state.kb import LiteratureKB
from src.tools.literature_kb import ListParsedPapersTool, ReadParsedPaperTool, SearchParsedPaperTool
from src.tools.mineru import MinerUConfig, mineru_evidence_chunks, run_mineru_for_kb
from src.tools.survey_context import PrepareSurveyContextTool
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

    def test_prepare_survey_context_returns_structure_and_citation_map(self) -> None:
        kb = LiteratureKB()
        first = kb.upsert_paper(title="World Models", year=2018)
        second = kb.upsert_paper(title="Benchmarking World Models", year=2024)
        kb.add_evidence(
            first,
            text="World models learn latent representations and dynamics for planning in simulated environments.",
            source="sciverse_semantic",
        )
        kb.add_evidence(
            second,
            text="Evaluation benchmarks compare performance, limitations, and generalization of model-based agents.",
            source="sciverse_semantic",
        )

        payload = json.loads(asyncio.run(PrepareSurveyContextTool(kb).execute(max_evidence=10)))

        self.assertIn("timeline", payload)
        self.assertIn("citation_map", payload)
        self.assertNotIn("taxonomy", payload)
        self.assertNotIn("recommended_outline", payload)
        self.assertEqual(payload["outline_status"], "llm_unavailable")
        self.assertEqual(payload["citation_map"][0]["evidence_id"], "P001-E01")
        self.assertEqual(payload["citation_map"][1]["evidence_id"], "P002-E01")

    def test_prepare_survey_context_sanitizes_llm_design(self) -> None:
        class FakeLLM:
            async def chat(self, messages, tools=None):
                return {
                    "content": json.dumps(
                        {
                            "selected_papers": [{"paper_id": "P001", "reason": "central"}],
                            "low_relevance_papers": [{"paper_id": "P999", "reason": "invented"}],
                            "evidence_needs": [
                                {
                                    "need": "More benchmark evidence",
                                    "suggested_tools": ["read_context", "external_library"],
                                }
                            ],
                            "recommended_outline": [
                                {
                                    "section": "Introduction",
                                    "purpose": "Define scope and motivation",
                                }
                            ],
                            "writing_plan": "Synthesize rather than enumerate.",
                        }
                    )
                }

        kb = LiteratureKB()
        paper = kb.upsert_paper(title="World Models", year=2018)
        kb.add_evidence(
            paper,
            text="World models learn latent representations and dynamics for planning.",
            source="sciverse_semantic",
        )

        payload = json.loads(asyncio.run(PrepareSurveyContextTool(kb, llm=FakeLLM()).execute()))

        self.assertEqual(payload["recommended_outline"], ["Introduction: Define scope and motivation"])
        self.assertEqual(payload["outline_status"], "generated_by_llm")
        self.assertEqual(payload["survey_design"]["low_relevance_papers"], [])
        self.assertEqual(
            payload["survey_design"]["evidence_needs"][0]["suggested_tools"],
            ["read_context"],
        )


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
        self.assertIsNotNone(kb.get_parsed_document("P001"))
        self.assertEqual(kb.evidence[0].source, "mineru_structured")
        self.assertIn("world model", kb.evidence[0].text)

    def test_parsed_paper_tools_read_and_search_mineru_text_as_evidence(self) -> None:
        kb = LiteratureKB()
        paper = kb.upsert_paper(title="World Models", year=2018)
        kb.set_parsed_document(
            paper,
            text=(
                "Introduction explains latent dynamics for planning.\n\n"
                "Evaluation discusses limitations, benchmark generalization, and model-based agents."
            ),
            source="mineru",
            metadata={"markdown_path": "paper/full.md"},
        )

        listed = asyncio.run(ListParsedPapersTool(kb).execute())
        read = asyncio.run(ReadParsedPaperTool(kb).execute("P001", offset=0, limit=80))
        searched = asyncio.run(SearchParsedPaperTool(kb).execute("P001", query="limitations benchmark", max_hits=2))

        self.assertIn("World Models", listed)
        self.assertIn("P001-E01", read)
        self.assertIn("P001-E02", searched)
        self.assertEqual(kb.evidence[0].source, "mineru_parsed_read")
        self.assertEqual(kb.evidence[1].source, "mineru_parsed_search")


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

    def test_skips_markdown_table_blocks_for_paragraph_citation_check(self) -> None:
        kb = LiteratureKB()
        paper = kb.upsert_paper(title="World Models")
        evidence = kb.add_evidence(paper, text=" ".join(["world"] * 40), source="sciverse_semantic")
        assert evidence is not None

        report = CitationVerifier(kb).validate_text(
            "# Survey\n\n"
            f"This evidence-backed paragraph is long enough to be checked and cites a known source [{evidence.evidence_id}].\n\n"
            "| Approach | Use |\n"
            "|---|---|\n"
            "| Latent dynamics | Planning |\n"
        )

        self.assertEqual(report.status, "pass")

    def test_does_not_require_evidence_ids_inside_references_section(self) -> None:
        kb = LiteratureKB()
        paper = kb.upsert_paper(title="World Models")
        evidence = kb.add_evidence(paper, text=" ".join(["world"] * 40), source="sciverse_semantic")
        assert evidence is not None

        report = CitationVerifier(kb).validate_text(
            "# Survey\n\n"
            f"This evidence-backed paragraph is long enough to be checked and cites a known source [{evidence.evidence_id}].\n\n"
            "## References\n\n"
            "P001: World Models (2018)\n"
            "P002: Another long reference entry that should not be treated as unsupported survey prose.\n"
        )

        self.assertEqual(report.status, "pass")

    def test_skips_figure_markup_for_paragraph_citation_check(self) -> None:
        kb = LiteratureKB()
        paper = kb.upsert_paper(title="World Models")
        evidence = kb.add_evidence(paper, text=" ".join(["world"] * 40), source="sciverse_semantic")
        assert evidence is not None

        report = CitationVerifier(kb).validate_text(
            "# Survey\n\n"
            "## Introduction\n\n"
            "<figure id=\"F001\">\n\n"
            "![Long Generated Figure Title That Would Otherwise Be Treated As A Paragraph](figures/figure.png)\n\n"
            f"<figcaption>Sources: {evidence.evidence_id}.</figcaption>\n\n"
            "</figure>\n\n"
            f"This evidence-backed paragraph is long enough to be checked and cites a known source [{evidence.evidence_id}].\n"
        )

        self.assertEqual(report.status, "pass")


if __name__ == "__main__":
    unittest.main()
