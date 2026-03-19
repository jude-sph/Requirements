import pytest
from src.loader import WorkbookData
from src.models import RequirementNode, RequirementTree
from src.validator import validate_tree_structure

@pytest.fixture
def ref_data():
    data = WorkbookData()
    data.system_hierarchy = [{"id": "SBS 700 (Trials)"}, {"id": "SBS 200 (Propulsion)"}]
    data.gtr_chapters = ["GTR-Ch 3: Whole Ship Performance"]
    data.sds_chapters = ["SDS-Ch 2: Propulsion & Manoeuvring"]
    return data

def _make_valid_tree():
    child = RequirementNode(
        level=2, level_name="Major System", allocation="SDS",
        chapter_code="SDS-Ch 2: Propulsion & Manoeuvring", derived_name="Propulsion",
        technical_requirement="The Propulsion System shall provide power.",
        rationale="R.", system_hierarchy_id="SBS 200 (Propulsion)",
        verification_method=["Analysis"], verification_event=["Design Review"],
        test_case_descriptions=["Review design."])
    root = RequirementNode(
        level=1, level_name="Whole Ship", allocation="GTR",
        chapter_code="GTR-Ch 3: Whole Ship Performance", derived_name="Speed",
        technical_requirement="The Vessel shall achieve 17 knots.",
        rationale="R.", system_hierarchy_id="SBS 700 (Trials)",
        verification_method=["Test"], verification_event=["Sea Trials"],
        test_case_descriptions=["Run speed trial."], children=[child])
    return RequirementTree(dig_id="9584", dig_text="Ship speed.", root=root)

class TestStructuralValidation:
    def test_valid_tree_passes(self, ref_data):
        tree = _make_valid_tree()
        errors = validate_tree_structure(tree, ref_data, max_depth=4, max_breadth=3)
        assert len(errors) == 0

    def test_missing_shall(self, ref_data):
        tree = _make_valid_tree()
        tree.root.technical_requirement = "The Vessel must achieve 17 knots."
        errors = validate_tree_structure(tree, ref_data, max_depth=4, max_breadth=3)
        assert any("shall" in e.message.lower() for e in errors)

    def test_invalid_chapter_code(self, ref_data):
        tree = _make_valid_tree()
        tree.root.chapter_code = "FAKE-Ch 99"
        errors = validate_tree_structure(tree, ref_data, max_depth=4, max_breadth=3)
        assert any("chapter" in e.message.lower() for e in errors)

    def test_vv_array_mismatch(self, ref_data):
        tree = _make_valid_tree()
        tree.root.verification_method = ["Test", "Analysis"]
        tree.root.verification_event = ["Sea Trials"]
        errors = validate_tree_structure(tree, ref_data, max_depth=4, max_breadth=3)
        assert any("mismatch" in e.message.lower() or "length" in e.message.lower() for e in errors)

    def test_child_level_not_parent_plus_one(self, ref_data):
        tree = _make_valid_tree()
        tree.root.children[0].level = 5
        errors = validate_tree_structure(tree, ref_data, max_depth=4, max_breadth=3)
        assert any("level" in e.message.lower() for e in errors)

    def test_exceeds_max_depth(self, ref_data):
        tree = _make_valid_tree()
        errors = validate_tree_structure(tree, ref_data, max_depth=1, max_breadth=3)
        assert any("depth" in e.message.lower() for e in errors)

    def test_exceeds_max_breadth(self, ref_data):
        tree = _make_valid_tree()
        for i in range(5):
            tree.root.children.append(RequirementNode(
                level=2, level_name="Major System", allocation="SDS",
                chapter_code="SDS-Ch 2: Propulsion & Manoeuvring",
                derived_name=f"Extra {i}",
                technical_requirement=f"The System shall do thing {i}.",
                rationale="R.", system_hierarchy_id="SBS 200 (Propulsion)"))
        errors = validate_tree_structure(tree, ref_data, max_depth=4, max_breadth=3)
        assert any("breadth" in e.message.lower() or "children" in e.message.lower() for e in errors)

    def test_tbd_without_notes(self, ref_data):
        tree = _make_valid_tree()
        tree.root.technical_requirement = "The Vessel shall provide [TBD] MW."
        tree.root.confidence_notes = None
        errors = validate_tree_structure(tree, ref_data, max_depth=4, max_breadth=3)
        assert any("TBD" in e.message or "confidence" in e.message.lower() for e in errors)
