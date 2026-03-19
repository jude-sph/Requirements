from unittest.mock import MagicMock, patch
import pytest
from src.cost_tracker import CostTracker
from src.loader import WorkbookData
from src.models import RequirementNode, RequirementTree
from src.verifier import apply_vv_to_tree


@pytest.fixture
def ref_data():
    data = WorkbookData()
    data.acceptance_phases = ["Phase 1 - Design Verification"]
    data.verification_methods = [{"name": "Test (T)", "description": "Testing"}]
    data.verification_events = [{"name": "Design Disclosure (DD)", "description": "DD"}]
    return data


@pytest.fixture
def simple_tree():
    child = RequirementNode(level=2, level_name="Major System", allocation="SDS",
        chapter_code="SDS-Ch 2", derived_name="Propulsion",
        technical_requirement="The Propulsion System shall provide power.",
        rationale="R.", system_hierarchy_id="SBS 200")
    root = RequirementNode(level=1, level_name="Whole Ship", allocation="GTR",
        chapter_code="GTR-Ch 3", derived_name="Speed",
        technical_requirement="The Vessel shall achieve 17 knots.",
        rationale="R.", system_hierarchy_id="SBS 700", children=[child])
    return RequirementTree(dig_id="9584", dig_text="Ship must do 17 knots.", root=root)


@patch("src.verifier.call_llm")
@patch("src.verifier.create_client")
def test_vv_applied_to_all_nodes(mock_create, mock_call, ref_data, simple_tree):
    mock_create.return_value = MagicMock()
    mock_call.return_value = {
        "acceptance_criteria": "Progressive verification across phases.",
        "verification_method": ["Analysis"],
        "verification_event": ["Design Disclosure"],
        "test_case_descriptions": ["Review design analysis."],
    }
    tracker = CostTracker(model="claude-sonnet-4-6")
    apply_vv_to_tree(simple_tree, ref_data, tracker)
    assert simple_tree.root.acceptance_criteria is not None
    assert len(simple_tree.root.verification_method) == 1
    assert simple_tree.root.children[0].acceptance_criteria is not None
    assert mock_call.call_count == 2
