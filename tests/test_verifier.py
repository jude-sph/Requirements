import json
from unittest.mock import MagicMock, patch
import pytest
from src.cost_tracker import CostTracker
from src.loader import WorkbookData
from src.models import RequirementNode, RequirementTree
from src.verifier import apply_vv_to_tree

def _make_mock_response(content: dict, input_tokens=800, output_tokens=400):
    resp = MagicMock()
    resp.content = [MagicMock()]
    resp.content[0].text = json.dumps(content)
    resp.usage = MagicMock()
    resp.usage.input_tokens = input_tokens
    resp.usage.output_tokens = output_tokens
    return resp

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

@patch("src.verifier.anthropic")
def test_vv_applied_to_all_nodes(mock_anthropic, ref_data, simple_tree):
    vv_response = _make_mock_response({
        "acceptance_criteria": "Progressive verification across phases.",
        "verification_method": ["Analysis"],
        "verification_event": ["Design Disclosure"],
        "test_case_descriptions": ["Review design analysis."],
    })
    mock_client = MagicMock()
    mock_client.messages.create.return_value = vv_response
    mock_anthropic.Anthropic.return_value = mock_client
    tracker = CostTracker(model="claude-sonnet-4-6")
    apply_vv_to_tree(simple_tree, ref_data, tracker)
    assert simple_tree.root.acceptance_criteria is not None
    assert len(simple_tree.root.verification_method) == 1
    assert simple_tree.root.children[0].acceptance_criteria is not None
    assert tracker.get_summary().api_calls == 2
