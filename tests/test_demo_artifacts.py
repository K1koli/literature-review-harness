from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from src.demo.artifacts import build_summary
from src.demo.pdf import write_review_pdf


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

    def test_demo_ui_only_exposes_generate_and_clears_prompt(self) -> None:
        root = Path(__file__).resolve().parents[1]
        index_html = (root / "src" / "demo" / "static" / "index.html").read_text(encoding="utf-8")
        app_js = (root / "src" / "demo" / "static" / "app.js").read_text(encoding="utf-8")

        self.assertNotIn("sampleButton", index_html)
        self.assertNotIn("样例", index_html)
        self.assertNotIn("/api/reviews/sample", app_js)
        self.assertIn('els.topic.value = "";', app_js)


if __name__ == "__main__":
    unittest.main()
