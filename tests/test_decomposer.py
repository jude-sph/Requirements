import json
from unittest.mock import MagicMock, patch
import pytest
from src.cost_tracker import CostTracker
from src.decomposer import decompose_dig
from src.loader import WorkbookData

def _make_mock_response(content: dict, input_tokens=1000, output_tokens=500):
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
    data.system_hierarchy = [{"id": "SBS 700 (Trials)"}, {"id": "SBS 200 (Propulsion)"}]
    data.gtr_chapters = ["GTR-Ch 3: Whole Ship Performance"]
    data.sds_chapters = ["SDS-Ch 2: Propulsion & Manoeuvring"]
    data.acceptance_phases = ["Phase 1 - Design Verification"]
    data.verification_methods = [{"name": "Test (T)", "description": "Testing"}]
    data.verification_events = [{"name": "Design Disclosure (DD)", "description": "DD"}]
    return data

@patch("src.decomposer.anthropic")
def test_single_level_decomposition(mock_anthropic, ref_data):
    l1_response = _make_mock_response({
        "children": [{"level": 1, "level_name": "Whole Ship", "allocation": "GTR",
            "chapter_code": "GTR-Ch 3: Whole Ship Performance", "derived_name": "Maximum Speed",
            "technical_requirement": "The Vessel shall achieve 17 knots.",
            "rationale": "DIG transposition.", "system_hierarchy_id": "SBS 700 (Trials)",
            "confidence_notes": None, "decomposition_complete": False}],
        "decomposition_complete": False,
    })
    l2_response = _make_mock_response({"children": [], "decomposition_complete": True})
    mock_client = MagicMock()
    mock_client.messages.create.side_effect = [l1_response, l2_response]
    mock_anthropic.Anthropic.return_value = mock_client
    tracker = CostTracker(model="claude-sonnet-4-6")
    tree = decompose_dig(dig_id="9584", dig_text="The ship must do 17 knots.",
        ref_data=ref_data, max_depth=2, max_breadth=3, skip_vv=True, cost_tracker=tracker)
    assert tree.root is not None
    assert tree.root.level == 1
    assert tree.root.technical_requirement == "The Vessel shall achieve 17 knots."
    assert tree.count_nodes() == 1
    assert tracker.get_summary().api_calls == 2

@patch("src.decomposer.anthropic")
def test_max_depth_respected(mock_anthropic, ref_data):
    l1_response = _make_mock_response({
        "children": [{"level": 1, "level_name": "Whole Ship", "allocation": "GTR",
            "chapter_code": "GTR-Ch 3: Whole Ship Performance", "derived_name": "Speed",
            "technical_requirement": "The Vessel shall do things.",
            "rationale": "Reason.", "system_hierarchy_id": "SBS 700 (Trials)",
            "confidence_notes": None, "decomposition_complete": False}],
        "decomposition_complete": False,
    })
    mock_client = MagicMock()
    mock_client.messages.create.return_value = l1_response
    mock_anthropic.Anthropic.return_value = mock_client
    tracker = CostTracker(model="claude-sonnet-4-6")
    tree = decompose_dig(dig_id="9584", dig_text="The ship must do stuff.",
        ref_data=ref_data, max_depth=1, max_breadth=3, skip_vv=True, cost_tracker=tracker)
    assert tree.root is not None
    assert tree.max_depth() == 1
