import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from src.images.generator import OpenAIImageGenerator
from src.images.generator import GeneratedImage
from src.images.pipeline import generate_survey_images, insert_figures_into_sections
from src.images.planner import FigurePlan, parse_markdown_sections, plan_survey_figures
from src.state.kb import LiteratureKB
from src.utils.config import Config


class ImageGenerationTest(unittest.TestCase):
    def test_insert_figures_into_sections_adds_relative_image_links_near_target_heading(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp)
            survey_path = output / "survey.md"
            image_path = output / "images" / "figure.png"
            image_path.parent.mkdir()
            image_path.write_bytes(b"png")
            survey_path.write_text("# Survey\n\n## Methods\n\nBody with evidence P001-E01.", encoding="utf-8")

            insert_figures_into_sections(
                survey_path,
                [
                    GeneratedImage(
                        figure_id="F001",
                        title="Conceptual Overview",
                        caption="Caption.",
                        prompt="Prompt.",
                        path=str(image_path),
                        model="gpt-image-1",
                        size="1536x1024",
                        quality="low",
                        target_heading="Methods",
                        source_evidence_ids=["P001-E01"],
                    )
                ],
            )

            survey = survey_path.read_text(encoding="utf-8")
            self.assertNotIn("## Illustrations", survey)
            self.assertIn("](images/figure.png)", survey)
            self.assertIn("F001. Conceptual Overview", survey)
            self.assertLess(survey.index("figure.png"), survey.index("Body with evidence"))
            self.assertNotIn("Sources:", survey)
            self.assertIn("Figure F001 summarizes", survey)

    def test_planner_uses_sections_citations_and_caps_figure_count(self) -> None:
        kb = LiteratureKB()
        paper = kb.upsert_paper(title="World Models", year=2018)
        kb.add_evidence(paper, text=" ".join(["latent dynamics"] * 40), source="test")
        survey = (
            "# Survey\n\n"
            "## 1. Introduction and Background\n\n"
            "World models are useful for prediction and planning [P001-E01].\n\n"
            "## 2. Key Approaches and Methods\n\n"
            "Latent and video approaches differ [P001-E01].\n\n"
            "## 3. Comparative Analysis\n\n"
            "Different representations trade off fidelity and grounding [P001-E01].\n"
        )

        plans = plan_survey_figures(topic="World Models", survey_markdown=survey, kb=kb, max_figures=2)

        self.assertEqual(len(plans), 2)
        self.assertEqual(plans[0].target_heading, "1. Introduction and Background")
        self.assertEqual(plans[0].render_mode, "image")
        self.assertEqual(plans[1].render_mode, "image")
        self.assertEqual(plans[0].figure_type, "literature_taxonomy_map")
        self.assertEqual(plans[0].source_evidence_ids, ["P001-E01"])

    def test_planner_can_select_multiple_section_figure_types(self) -> None:
        kb = LiteratureKB()
        paper = kb.upsert_paper(title="World Models", year=2018)
        kb.add_evidence(paper, text=" ".join(["robotics evaluation future planning"] * 20), source="test")
        survey = (
            "# Survey\n\n"
            "## 1. Introduction\n\nIntro [P001-E01].\n\n"
            "## 2. Method Families and Architectures\n\nMethods [P001-E01].\n\n"
            "## 3. Applications Across RL Domains\n\nApplications [P001-E01].\n\n"
            "## 4. Evaluation Methodologies and Benchmarks\n\nEvaluation [P001-E01].\n\n"
            "## 5. Future Research Directions\n\nFuture [P001-E01].\n"
        )

        plans = plan_survey_figures(topic="World Models", survey_markdown=survey, kb=kb, max_figures=4)

        self.assertEqual(len(plans), 4)
        self.assertIn("application_map", {plan.figure_type for plan in plans})
        self.assertIn("comparison_matrix", {plan.figure_type for plan in plans})

    def test_section_parser_includes_child_headings_in_parent_body(self) -> None:
        survey = (
            "# Survey\n\n"
            "## 2. Key Approaches and Methods\n\n"
            "### 2.1 Latent Methods\n\n"
            "Subsection evidence should belong to the parent section [P001-E01].\n\n"
            "## 3. Comparative Analysis\n\n"
            "Next parent section [P002-E01].\n"
        )

        sections = parse_markdown_sections(survey)
        methods = next(section for section in sections if section.title == "2. Key Approaches and Methods")

        self.assertEqual(methods.evidence_ids, ["P001-E01"])
        self.assertIn("Latent Methods", methods.body)

    def test_pipeline_falls_back_to_svg_when_raster_generation_has_no_key(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            result = self._run(
                generate_survey_images(
                    config=Config(image_generation_enabled=True, openai_image_api_key=""),
                    topic="World Models",
                    survey_markdown="# Survey",
                    kb=LiteratureKB(),
                    output_dir=Path(tmp),
                    figure_plans=[
                        FigurePlan(
                            figure_id="F001",
                            title="Conceptual Overview",
                            caption="Caption.",
                            target_heading="Survey",
                            figure_type="conceptual_overview",
                            render_mode="image",
                            source_evidence_ids=[],
                            filename="figure_001_conceptual_overview.png",
                            prompt="Prompt.",
                        )
                    ],
                )
            )

            self.assertIsNone(result.skipped_reason)
            self.assertEqual(len(result.generated), 1)
            self.assertEqual(result.generated[0].render_mode, "svg")
            self.assertIn("OpenAI image API key is required", result.errors[0]["error"])
            self.assertIn("used local SVG fallback", result.errors[1]["error"])

    def test_generator_builds_configurable_generation_url(self) -> None:
        generator = OpenAIImageGenerator(
            api_key="test-key",
            base_url="https://api.example.test/v1",
            endpoint_path="/images/generations",
        )
        full_url_generator = OpenAIImageGenerator(
            api_key="test-key",
            base_url="https://api.example.test/v1/images/generations",
            endpoint_path="/ignored",
        )

        self.assertEqual(generator._generation_url(), "https://api.example.test/v1/images/generations")
        self.assertEqual(
            full_url_generator._generation_url(),
            "https://api.example.test/v1/images/generations",
        )

    def test_generator_accepts_model_fallback_list(self) -> None:
        generator = OpenAIImageGenerator(
            api_key="test-key",
            model="first-model",
            models=["first-model", "second-model", "first-model"],
        )

        self.assertEqual(generator.models, ["first-model", "second-model"])

    def test_generator_uses_supported_size_for_dalle3_fallback(self) -> None:
        generator = OpenAIImageGenerator(api_key="test-key", models=["dall-e-3"], size="1536x1024")

        self.assertEqual(generator.models, ["dall-e-3"])
        from src.images.generator import _size_for_model

        self.assertEqual(_size_for_model("dall-e-3", generator.size), "1024x1024")
        self.assertEqual(_size_for_model("gpt-image-2", generator.size), "1536x1024")

    def test_pipeline_writes_manifest_with_fake_generator(self) -> None:
        class FakeGenerator:
            def __init__(self, **kwargs):
                self.kwargs = kwargs

            async def generate(self, spec, output_dir):
                output_dir.mkdir(parents=True, exist_ok=True)
                path = output_dir / spec.filename
                path.write_bytes(b"fake-image")
                return GeneratedImage(
                    figure_id=spec.figure_id,
                    title=spec.title,
                    caption=spec.caption,
                    prompt=spec.prompt,
                    path=str(path),
                    model=self.kwargs["model"],
                    size=self.kwargs["size"],
                    quality=self.kwargs["quality"],
                )

        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp)
            survey_path = output / "survey.md"
            survey_path.write_text("# Survey\n\n## Intro\n\nBody P001-E01.", encoding="utf-8")
            stale = output / "figures" / "figure_999_old.svg"
            stale.parent.mkdir()
            stale.write_text("<svg/>", encoding="utf-8")
            config = Config(
                image_generation_enabled=True,
                openai_image_api_key="test-key",
                image_generation_count=1,
            )

            with patch("src.images.pipeline.OpenAIImageGenerator", FakeGenerator):
                result = self._run(
                    generate_survey_images(
                        config=config,
                        topic="World Models",
                        survey_markdown="# World Models Survey",
                        kb=LiteratureKB(),
                        output_dir=output,
                        survey_path=survey_path,
                        figure_plans=[
                            FigurePlan(
                                figure_id="F001",
                                title="Conceptual Overview",
                                caption="Caption.",
                                target_heading="Intro",
                                figure_type="conceptual_overview",
                                render_mode="image",
                                source_evidence_ids=["P001-E01"],
                                filename="figure_001_conceptual_overview.png",
                                prompt="Prompt.",
                            )
                        ],
                    )
            )

            self.assertEqual(len(result.generated), 1)
            self.assertEqual(result.generated[0].model, "gpt-image-1")
            self.assertTrue((output / "figures" / "figure_manifest.json").exists())
            self.assertTrue((output / "figure_plan.json").exists())
            self.assertFalse(stale.exists())
            self.assertIn("figure_001_conceptual_overview.png", survey_path.read_text(encoding="utf-8"))

    def _run(self, awaitable):
        import asyncio

        return asyncio.run(awaitable)


if __name__ == "__main__":
    unittest.main()
