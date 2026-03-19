import pytest
from src.models import RequirementNode, RequirementTree, CostEntry, CostSummary, ValidationResult


class TestRequirementNode:
    def test_minimal_leaf_node(self):
        node = RequirementNode(
            level=1,
            level_name="Whole Ship",
            allocation="GTR",
            chapter_code="GTR-Ch 3",
            derived_name="Max Speed",
            technical_requirement="The Vessel shall achieve 17 knots.",
            rationale="Transposition of DIG.",
            system_hierarchy_id="SBS 700 (Trials)",
        )
        assert node.level == 1
        assert node.children == []
        assert node.decomposition_complete is False
        assert node.confidence_notes is None
        assert node.acceptance_criteria is None

    def test_node_with_vv_data(self):
        node = RequirementNode(
            level=2,
            level_name="Major System",
            allocation="SDS",
            chapter_code="SDS-Ch 2",
            derived_name="Propulsion Power",
            technical_requirement="The Propulsion System shall provide [TBD] MW.",
            rationale="Power requirement.",
            system_hierarchy_id="SBS 200 (Propulsion)",
            acceptance_criteria="Phase 1 design review, Phase 4 sea trials.",
            verification_method=["Analysis", "Test"],
            verification_event=["Design Review", "Sea Trials"],
            test_case_descriptions=["Review analysis docs.", "Conduct sea trial."],
            confidence_notes="Power value TBD - requires propulsion study",
        )
        assert len(node.verification_method) == 2
        assert len(node.test_case_descriptions) == 2

    def test_node_with_children(self):
        child = RequirementNode(
            level=2, level_name="Major System", allocation="SDS",
            chapter_code="SDS-Ch 2", derived_name="Propulsion",
            technical_requirement="The Propulsion System shall provide power.",
            rationale="Needed for speed.", system_hierarchy_id="SBS 200 (Propulsion)",
        )
        parent = RequirementNode(
            level=1, level_name="Whole Ship", allocation="GTR",
            chapter_code="GTR-Ch 3", derived_name="Speed",
            technical_requirement="The Vessel shall achieve 17 knots.",
            rationale="DIG requirement.", system_hierarchy_id="SBS 700 (Trials)",
            children=[child],
        )
        assert len(parent.children) == 1
        assert parent.children[0].level == 2

    def test_vv_array_length_mismatch_raises(self):
        with pytest.raises(ValueError):
            RequirementNode(
                level=1, level_name="Whole Ship", allocation="GTR",
                chapter_code="GTR-Ch 3", derived_name="Speed",
                technical_requirement="The Vessel shall achieve 17 knots.",
                rationale="DIG requirement.", system_hierarchy_id="SBS 700 (Trials)",
                verification_method=["Analysis", "Test"],
                verification_event=["Design Review"],
                test_case_descriptions=["Review docs."],
            )

    def test_tbd_without_confidence_notes_raises(self):
        with pytest.raises(ValueError):
            RequirementNode(
                level=1, level_name="Whole Ship", allocation="GTR",
                chapter_code="GTR-Ch 3", derived_name="Speed",
                technical_requirement="The Vessel shall provide [TBD] MW.",
                rationale="Reason.", system_hierarchy_id="SBS 700 (Trials)",
                confidence_notes=None,
            )

    def test_invalid_allocation_raises(self):
        with pytest.raises(ValueError):
            RequirementNode(
                level=1, level_name="Whole Ship", allocation="INVALID",
                chapter_code="GTR-Ch 3", derived_name="Speed",
                technical_requirement="The Vessel shall do something.",
                rationale="Reason.", system_hierarchy_id="SBS 700 (Trials)",
            )


class TestRequirementTree:
    def test_tree_creation(self):
        root = RequirementNode(
            level=1, level_name="Whole Ship", allocation="GTR",
            chapter_code="GTR-Ch 3", derived_name="Speed",
            technical_requirement="The Vessel shall achieve 17 knots.",
            rationale="DIG transposition.", system_hierarchy_id="SBS 700 (Trials)",
        )
        tree = RequirementTree(dig_id="9584", dig_text="The ship must do 17 knots.", root=root)
        assert tree.dig_id == "9584"
        assert tree.root.level == 1

    def test_count_nodes(self):
        child = RequirementNode(
            level=2, level_name="Major System", allocation="SDS",
            chapter_code="SDS-Ch 2", derived_name="Propulsion",
            technical_requirement="The system shall provide power.",
            rationale="R.", system_hierarchy_id="SBS 200",
        )
        root = RequirementNode(
            level=1, level_name="Whole Ship", allocation="GTR",
            chapter_code="GTR-Ch 3", derived_name="Speed",
            technical_requirement="The Vessel shall achieve 17 knots.",
            rationale="R.", system_hierarchy_id="SBS 700",
            children=[child],
        )
        tree = RequirementTree(dig_id="9584", dig_text="Ship must do 17 knots.", root=root)
        assert tree.count_nodes() == 2

    def test_max_depth(self):
        grandchild = RequirementNode(
            level=3, level_name="Subsystem", allocation="SDS",
            chapter_code="SDS-Ch 4", derived_name="Propulsor",
            technical_requirement="Each propulsor shall output [TBD] kW.",
            rationale="R.", system_hierarchy_id="SBS 234",
            confidence_notes="Value TBD.",
        )
        child = RequirementNode(
            level=2, level_name="Major System", allocation="SDS",
            chapter_code="SDS-Ch 2", derived_name="Propulsion",
            technical_requirement="The system shall provide power.",
            rationale="R.", system_hierarchy_id="SBS 200",
            children=[grandchild],
        )
        root = RequirementNode(
            level=1, level_name="Whole Ship", allocation="GTR",
            chapter_code="GTR-Ch 3", derived_name="Speed",
            technical_requirement="The Vessel shall achieve 17 knots.",
            rationale="R.", system_hierarchy_id="SBS 700",
            children=[child],
        )
        tree = RequirementTree(dig_id="9584", dig_text="Ship.", root=root)
        assert tree.max_depth() == 3


class TestCostEntry:
    def test_cost_entry(self):
        entry = CostEntry(
            call_type="decompose", level=1,
            input_tokens=3200, output_tokens=620, cost_usd=0.0189,
        )
        assert entry.call_type == "decompose"
        assert entry.cost_usd == 0.0189


class TestCostSummary:
    def test_summary_totals(self):
        entries = [
            CostEntry(call_type="decompose", level=1, input_tokens=3000, output_tokens=600, cost_usd=0.018),
            CostEntry(call_type="vv", level=1, input_tokens=2500, output_tokens=500, cost_usd=0.015),
        ]
        summary = CostSummary(breakdown=entries)
        assert summary.total_input_tokens == 5500
        assert summary.total_output_tokens == 1100
        assert summary.total_cost_usd == pytest.approx(0.033)
        assert summary.api_calls == 2
