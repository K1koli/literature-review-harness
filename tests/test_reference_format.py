from __future__ import annotations

import unittest

from src.state.kb import LiteratureKB
from src.validation.references import format_numbered_references


class ReferenceFormatTest(unittest.TestCase):
    def test_formats_evidence_ids_as_numbered_paper_references(self) -> None:
        kb = LiteratureKB()
        first = kb.upsert_paper(title="World Models", year=2018, authors=["David Ha", "Jürgen Schmidhuber"])
        second = kb.upsert_paper(title="Learning Latent Dynamics for Planning from Pixels", year=2019)
        first_evidence = kb.add_evidence(first, text="World models learn latent dynamics for imagination.", source="test")
        second_evidence = kb.add_evidence(second, text="Latent dynamics support planning from pixels.", source="test")
        assert first_evidence is not None
        assert second_evidence is not None

        formatted = format_numbered_references(
            "# Survey\n\n"
            f"World models combine representation and dynamics [{first_evidence.evidence_id}, {second_evidence.evidence_id}].\n\n"
            "<references>\n"
            f"<evidence>{first_evidence.evidence_id}</evidence>\n"
            "</references>\n\n"
            "## References\n\n"
            f"- Old evidence reference [{first_evidence.evidence_id}]\n",
            kb,
        )

        self.assertIn("World models combine representation and dynamics [1, 2].", formatted)
        self.assertIn("[1] World Models. David Ha, Jürgen Schmidhuber. 2018. paper_id: P001.", formatted)
        self.assertIn("[2] Learning Latent Dynamics for Planning from Pixels. 2019. paper_id: P002.", formatted)
        self.assertNotIn("<references>", formatted)
        self.assertNotIn(first_evidence.evidence_id, formatted)

    def test_strips_sources_from_figure_captions(self) -> None:
        kb = LiteratureKB()
        first = kb.upsert_paper(title="World Models", year=2018)
        second = kb.upsert_paper(title="Planning from Pixels", year=2019)
        first_evidence = kb.add_evidence(first, text="World models learn latent dynamics.", source="test")
        second_evidence = kb.add_evidence(second, text="Latent dynamics support planning.", source="test")
        assert first_evidence is not None
        assert second_evidence is not None

        formatted = format_numbered_references(
            f"<figcaption>Figure caption. Sources: {first_evidence.evidence_id}, {second_evidence.evidence_id}.</figcaption>\n\n"
            f"Main claim [{first_evidence.evidence_id}].",
            kb,
        )

        self.assertIn("<figcaption>Figure caption.</figcaption>", formatted)
        self.assertNotIn("Sources:", formatted)

    def test_cleans_existing_references_with_unreadable_author_metadata(self) -> None:
        kb = LiteratureKB()
        paper = kb.upsert_paper(
            title="World Models",
            year=2018,
            authors=["[[108 101 111] [114 111 98 101 114 116]]"],
        )
        kb.add_evidence(paper, text="World models learn latent dynamics.", source="test")

        formatted = format_numbered_references(
            "Claim [1].\n\n"
            "<figcaption>Figure caption. Sources: [1, 1], [1].</figcaption>\n\n"
            "## References\n\n"
            "[1] Bad authors. [[108 101 111]]. paper_id: P001.\n",
            kb,
        )

        self.assertIn("<figcaption>Figure caption.</figcaption>", formatted)
        self.assertIn("[1] World Models. 2018. paper_id: P001.", formatted)
        self.assertNotIn("[[108", formatted)

    def test_collapses_duplicate_papers_by_title_and_year(self) -> None:
        kb = LiteratureKB()
        first = kb.upsert_paper(title="World Models", year=2018)
        duplicate = kb.upsert_paper(title="World Models", year=2018, doc_id="duplicate")
        first_evidence = kb.add_evidence(first, text="First evidence.", source="test")
        duplicate_evidence = kb.add_evidence(duplicate, text="Duplicate evidence.", source="test")
        assert first_evidence is not None
        assert duplicate_evidence is not None

        formatted = format_numbered_references(
            f"Same paper appears through two evidence records [{first_evidence.evidence_id}, {duplicate_evidence.evidence_id}].",
            kb,
        )

        self.assertIn("[1].", formatted)
        self.assertEqual(formatted.count("paper_id:"), 1)


if __name__ == "__main__":
    unittest.main()
