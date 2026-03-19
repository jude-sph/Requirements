import pytest
from src.prompts import format_decompose_prompt, format_vv_prompt, format_judge_prompt


class TestFormatDecomposePrompt:
    def test_loads_and_formats(self):
        result = format_decompose_prompt(
            dig_id="9584", dig_text="The ship must do 17 knots.",
            target_level=2, target_level_name="Major System",
            parent_scope="Whole Ship", child_scope="Major System",
            parent_chain="Level 1: The Vessel shall...",
            system_hierarchy="SBS 200 (Propulsion)",
            chapter_list="SDS-Ch 2", max_breadth=3)
        assert "9584" in result
        assert "Major System" in result
        assert "17 knots" in result
        assert "shall" in result.lower()

    def test_includes_levels_example(self):
        result = format_decompose_prompt(
            dig_id="1", dig_text="text", target_level=1,
            target_level_name="Whole Ship", parent_scope="DIG",
            child_scope="Whole Ship", parent_chain="",
            system_hierarchy="", chapter_list="", max_breadth=3)
        assert "Decomposition Levels Example" in result


class TestFormatVvPrompt:
    def test_loads_and_formats(self):
        result = format_vv_prompt(
            level=1, level_name="Whole Ship",
            technical_requirement="The Vessel shall achieve 17 knots.",
            system_hierarchy_id="SBS 700",
            acceptance_phases="Phase 1", verification_methods="Test",
            verification_events="Sea Trials")
        assert "17 knots" in result
        assert "Phase 1" in result


class TestFormatJudgePrompt:
    def test_loads_and_formats(self):
        result = format_judge_prompt(
            dig_id="9584", dig_text="Ship speed.",
            tree_json='{"root": {}}')
        assert "9584" in result
        assert "independent requirements reviewer" in result.lower()
