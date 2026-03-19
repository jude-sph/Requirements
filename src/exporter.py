import logging
from pathlib import Path
from openpyxl import Workbook
from src.models import RequirementNode, RequirementTree

logger = logging.getLogger(__name__)

COLUMNS = [
    "dig_id", "dig_text", "node_id", "parent_id", "level", "level_name",
    "allocation", "chapter_code", "derived_name", "technical_requirement",
    "rationale", "system_hierarchy_id", "confidence_notes",
    "acceptance_criteria", "verification_method", "verification_event",
    "test_case_descriptions",
]

def tree_to_rows(tree: RequirementTree) -> list[dict]:
    rows = []
    if not tree.root:
        return rows
    counter = [0]
    def _flatten(node: RequirementNode, parent_id: str) -> None:
        counter[0] += 1
        node_id = f"{tree.dig_id}-{counter[0]}"
        rows.append({
            "dig_id": tree.dig_id, "dig_text": tree.dig_text,
            "node_id": node_id, "parent_id": parent_id,
            "level": node.level, "level_name": node.level_name,
            "allocation": node.allocation, "chapter_code": node.chapter_code,
            "derived_name": node.derived_name,
            "technical_requirement": node.technical_requirement,
            "rationale": node.rationale,
            "system_hierarchy_id": node.system_hierarchy_id,
            "confidence_notes": node.confidence_notes or "",
            "acceptance_criteria": node.acceptance_criteria or "",
            "verification_method": ", ".join(node.verification_method),
            "verification_event": ", ".join(node.verification_event),
            "test_case_descriptions": " | ".join(node.test_case_descriptions),
        })
        for child in node.children:
            _flatten(child, node_id)
    _flatten(tree.root, "")
    return rows

def export_trees_to_xlsx(trees: list[RequirementTree], output_path: Path) -> None:
    wb = Workbook()
    ws = wb.active
    ws.title = "Decomposed Requirements"
    ws.append(COLUMNS)
    for tree in trees:
        for row in tree_to_rows(tree):
            ws.append([row.get(col, "") for col in COLUMNS])
    output_path.parent.mkdir(parents=True, exist_ok=True)
    wb.save(output_path)
    logger.info(f"Exported {sum(t.count_nodes() for t in trees)} requirements to {output_path}")
