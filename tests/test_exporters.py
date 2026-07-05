from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from src.exporters.html import export_html


class ExporterTest(unittest.TestCase):
    def test_html_export_renders_markdown_tables_and_ordered_lists(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            markdown = root / "survey.md"
            html = root / "survey.html"
            markdown.write_text(
                "# Survey\n\n"
                "1. First contribution [P001-E01]\n"
                "2. Second contribution [P001-E01]\n\n"
                "| Method | Source |\n"
                "|---|---|\n"
                "| World model | P001-E01 |\n",
                encoding="utf-8",
            )

            export_html(markdown, html, title="Survey")
            rendered = html.read_text(encoding="utf-8")

            self.assertIn("<ol>", rendered)
            self.assertIn("<table>", rendered)
            self.assertIn("<th>Method</th>", rendered)
            self.assertIn('<code class="evidence-id">P001-E01</code>', rendered)


if __name__ == "__main__":
    unittest.main()
