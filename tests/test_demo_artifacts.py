from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from src.demo.artifacts import build_summary, load_review_payload
from src.demo.pdf import write_pdf_page_previews, write_review_pdf


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

    def test_build_summary_keeps_all_cited_evidence(self) -> None:
        evidence = []
        cited_ids = []
        for index in range(1, 86):
            evidence_id = f"P{index:03d}-E01"
            cited_ids.append(evidence_id)
            evidence.append(
                {
                    "evidence_id": evidence_id,
                    "paper_id": f"P{index:03d}",
                    "title": f"Paper {index}",
                    "year": 2024,
                    "source": "test",
                    "text": "Evidence text.",
                }
            )
        evidence_pack = {"papers": [], "evidence": evidence}
        check_report = {"status": "pass", "errors": [], "cited_evidence_ids": cited_ids}

        summary = build_summary("# Survey", evidence_pack, check_report, [])

        self.assertEqual(summary["cited_evidence_count"], 85)
        self.assertEqual(len(summary["cited_evidence"]), 85)
        self.assertEqual(summary["cited_evidence"][-1]["evidence_id"], "P085-E01")

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

    def test_pdf_page_previews_are_exposed_in_payload(self) -> None:
        markdown = "# World Models\n\nWorld models support latent planning [P001-E01]."
        summary = {"paper_count": 1, "evidence_count": 1, "cited_evidence_count": 1, "year_counts": []}
        check_report = {"status": "pass", "cited_evidence_ids": ["P001-E01"]}

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            output_path = root / "survey.pdf"
            write_review_pdf(
                markdown=markdown,
                summary=summary,
                check_report=check_report,
                topic="World Models",
                output_path=output_path,
            )
            pages = write_pdf_page_previews(output_path, root / "pdf_pages", max_pages=1)
            if not pages:
                self.skipTest("pdftoppm is not available")
            (root / "survey.md").write_text(markdown, encoding="utf-8")
            (root / "evidence_pack.json").write_text('{"papers":[],"evidence":[]}', encoding="utf-8")
            (root / "check_report.json").write_text('{"status":"pass","cited_evidence_ids":["P001-E01"]}', encoding="utf-8")

            payload = load_review_payload("run123", root, "World Models", "completed")

            self.assertEqual(payload["downloads"]["pdf_pages"], ["/api/reviews/run123/asset/pdf_pages/page-1.png"])

    def test_demo_ui_only_exposes_generate_and_clears_prompt(self) -> None:
        root = Path(__file__).resolve().parents[1]
        index_html = (root / "src" / "demo" / "static" / "index.html").read_text(encoding="utf-8")
        app_js = (root / "src" / "demo" / "static" / "app.js").read_text(encoding="utf-8")

        self.assertNotIn("sampleButton", index_html)
        self.assertNotIn("样例", index_html)
        self.assertNotIn("/api/reviews/sample", app_js)
        self.assertIn('els.topic.value = "";', app_js)
        self.assertIn("event.skipped_reason", app_js)
        self.assertIn("issue(s)", app_js)


if __name__ == "__main__":
    unittest.main()
