from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from src.demo.artifacts import build_summary
from src.demo.pdf import write_review_pdf
from src.demo.sample import existing_sample_is_ready, write_fallback_sample


class DemoArtifactsTest(unittest.TestCase):
    def test_build_summary_counts_evidence_and_citations(self) -> None:
        markdown = "# World Models\n\nWorld models support latent planning [P001-E01]."
        evidence_pack = {
            "papers": [
                {
                    "paper_id": "P001",
                    "title": "World Models",
                    "year": 2018,
                    "venue": "arXiv",
                    "evidence_ids": ["P001-E01"],
                    "mineru": {"state": "skipped"},
                }
            ],
            "evidence": [
                {
                    "evidence_id": "P001-E01",
                    "paper_id": "P001",
                    "title": "World Models",
                    "year": 2018,
                    "source": "sciverse_semantic",
                    "text": "A compact world model can support planning in latent space.",
                }
            ],
        }
        check_report = {"status": "pass", "errors": [], "cited_evidence_ids": ["P001-E01"]}

        summary = build_summary(markdown, evidence_pack, check_report, [])

        self.assertEqual(summary["paper_count"], 1)
        self.assertEqual(summary["evidence_count"], 1)
        self.assertEqual(summary["cited_evidence_count"], 1)
        self.assertEqual(summary["citation_status"], "pass")
        self.assertEqual(summary["cited_evidence"][0]["evidence_id"], "P001-E01")

    def test_write_review_pdf_creates_downloadable_pdf(self) -> None:
        markdown = "# World Models\n\nWorld models support latent planning [P001-E01]."
        summary = {
            "paper_count": 1,
            "evidence_count": 1,
            "cited_evidence_count": 1,
            "year_counts": [{"label": "2018", "count": 1}],
            "source_counts": [{"label": "sciverse_semantic", "count": 1}],
        }
        check_report = {"status": "pass"}

        with tempfile.TemporaryDirectory() as tmp:
            output_path = Path(tmp) / "survey.pdf"
            write_review_pdf(
                markdown=markdown,
                summary=summary,
                check_report=check_report,
                topic="World Models",
                output_path=output_path,
            )

            payload = output_path.read_bytes()
            self.assertTrue(payload.startswith(b"%PDF"))
            self.assertGreater(len(payload), 300)

    def test_fallback_sample_writes_demo_article_and_figure(self) -> None:
        evidence_pack = {
            "papers": [
                {
                    "paper_id": "P001",
                    "title": "World Models",
                    "year": 2018,
                    "evidence_ids": ["P001-E01"],
                }
            ],
            "evidence": [
                {
                    "evidence_id": "P001-E01",
                    "paper_id": "P001",
                    "title": "World Models",
                    "year": 2018,
                    "source": "sciverse_semantic",
                    "text": "World models learn compact environment representations for planning.",
                }
            ],
        }
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            pack_path = root / "evidence_pack.json"
            pack_path.write_text(json.dumps(evidence_pack), encoding="utf-8")
            output_dir = root / "demo"

            write_fallback_sample(topic="World Models", evidence_pack_path=pack_path, output_dir=output_dir)

            markdown = (output_dir / "survey.md").read_text(encoding="utf-8")
            self.assertIn("![Evidence-grounded harness flow](figures/sample_harness_flow.svg)", markdown)
            self.assertIn("P001-E01", markdown)
            self.assertTrue((output_dir / "figures" / "sample_harness_flow.svg").exists())
            self.assertTrue(existing_sample_is_ready(output_dir))


if __name__ == "__main__":
    unittest.main()
