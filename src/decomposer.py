import json
import logging
import time
import anthropic
from src.config import ANTHROPIC_API_KEY, MODEL, LEVEL_NAMES
from src.cost_tracker import CostTracker
from src.loader import WorkbookData
from src.models import RequirementNode, RequirementTree
from src.prompts import format_decompose_prompt

logger = logging.getLogger(__name__)
MAX_RETRIES = 3
RETRY_DELAYS = [1, 2, 4]

def _call_api(client: anthropic.Anthropic, prompt: str, cost_tracker: CostTracker, call_type: str, level: int) -> dict:
    for attempt in range(MAX_RETRIES):
        try:
            logger.debug(f"API call: {call_type} L{level} (attempt {attempt + 1})")
            logger.debug(f"Prompt length: {len(prompt)} chars")
            resp = client.messages.create(model=MODEL, max_tokens=4096, messages=[{"role": "user", "content": prompt}])
            text = resp.content[0].text
            logger.debug(f"Response length: {len(text)} chars")
            cost_tracker.record(call_type=call_type, level=level, input_tokens=resp.usage.input_tokens, output_tokens=resp.usage.output_tokens)
            if "```json" in text:
                text = text.split("```json")[1].split("```")[0]
            elif "```" in text:
                text = text.split("```")[1].split("```")[0]
            return json.loads(text.strip())
        except (anthropic.APIError, anthropic.APIConnectionError, anthropic.RateLimitError) as e:
            if attempt < MAX_RETRIES - 1:
                delay = RETRY_DELAYS[attempt]
                logger.warning(f"API error (attempt {attempt + 1}): {e}. Retrying in {delay}s...")
                time.sleep(delay)
            else:
                logger.error(f"API call failed after {MAX_RETRIES} attempts: {e}")
                raise
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse JSON from API response: {e}")
            logger.debug(f"Raw response: {text}")
            raise

def _format_ref_data(ref_data: WorkbookData) -> dict:
    hierarchy_str = "\n".join(h["id"] for h in ref_data.system_hierarchy)
    gtr_str = "\n".join(ref_data.gtr_chapters)
    sds_str = "\n".join(ref_data.sds_chapters)
    return {
        "system_hierarchy": hierarchy_str,
        "all_chapters": f"### GTR Chapters\n{gtr_str}\n\n### SDS Chapters\n{sds_str}",
        "acceptance_phases": "\n\n".join(ref_data.acceptance_phases),
        "verification_methods": "\n".join(f"- {m['name']}: {m['description']}" for m in ref_data.verification_methods),
        "verification_events": "\n".join(f"- {e['name']}: {e['description']}" for e in ref_data.verification_events),
    }

def _build_parent_chain(ancestors: list[RequirementNode]) -> str:
    if not ancestors:
        return "(This is the first level — no parent requirements yet.)"
    lines = []
    for node in ancestors:
        lines.append(f"Level {node.level} ({node.level_name}):\n  Requirement: {node.technical_requirement}\n  Allocation: {node.allocation}\n  System: {node.system_hierarchy_id}\n  Chapter: {node.chapter_code}")
    return "\n\n".join(lines)

def decompose_dig(dig_id: str, dig_text: str, ref_data: WorkbookData, max_depth: int, max_breadth: int, skip_vv: bool, cost_tracker: CostTracker) -> RequirementTree:
    logger.info(f'Decomposing DIG {dig_id}: "{dig_text[:80]}..."')
    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
    refs = _format_ref_data(ref_data)
    tree = RequirementTree(dig_id=dig_id, dig_text=dig_text)
    root_children = _decompose_level(client=client, dig_id=dig_id, dig_text=dig_text, target_level=1, ancestors=[], refs=refs, max_breadth=max_breadth, cost_tracker=cost_tracker)
    if not root_children:
        logger.warning(f"DIG {dig_id}: No Level 1 requirements generated")
        return tree
    root = root_children[0]
    tree.root = root
    if max_depth > 1:
        _decompose_children(client=client, dig_id=dig_id, dig_text=dig_text, parent=root, ancestors=[root], refs=refs, max_depth=max_depth, max_breadth=max_breadth, cost_tracker=cost_tracker)
    return tree

def _decompose_level(client, dig_id, dig_text, target_level, ancestors, refs, max_breadth, cost_tracker):
    target_name = LEVEL_NAMES.get(target_level, f"Level {target_level}")
    parent_name = LEVEL_NAMES.get(target_level - 1, "DIG") if target_level > 1 else "DIG"
    prompt = format_decompose_prompt(dig_id=dig_id, dig_text=dig_text, target_level=target_level, target_level_name=target_name, parent_scope=parent_name, child_scope=target_name, parent_chain=_build_parent_chain(ancestors), system_hierarchy=refs["system_hierarchy"], chapter_list=refs["all_chapters"], max_breadth=max_breadth)
    result = _call_api(client, prompt, cost_tracker, "decompose", target_level)
    if result.get("decomposition_complete", False):
        logger.info(f"  L{target_level}: Decomposition complete (no further breakdown)")
        return []
    children = []
    for child_data in result.get("children", [])[:max_breadth]:
        try:
            node = RequirementNode(level=child_data.get("level", target_level), level_name=child_data.get("level_name", target_name), allocation=child_data.get("allocation", "Information Not Found"), chapter_code=child_data.get("chapter_code", "Information Not Found"), derived_name=child_data.get("derived_name", ""), technical_requirement=child_data.get("technical_requirement", ""), rationale=child_data.get("rationale", ""), system_hierarchy_id=child_data.get("system_hierarchy_id", "Information Not Found"), confidence_notes=child_data.get("confidence_notes"), decomposition_complete=child_data.get("decomposition_complete", False))
            children.append(node)
            logger.info(f'  L{target_level} ({node.allocation}): "{node.technical_requirement[:60]}..."')
        except Exception as e:
            logger.error(f"  L{target_level}: Failed to parse child: {e}")
    return children

def _decompose_children(client, dig_id, dig_text, parent, ancestors, refs, max_depth, max_breadth, cost_tracker):
    if parent.level >= max_depth:
        return
    if parent.decomposition_complete:
        return
    children = _decompose_level(client=client, dig_id=dig_id, dig_text=dig_text, target_level=parent.level + 1, ancestors=ancestors, refs=refs, max_breadth=max_breadth, cost_tracker=cost_tracker)
    parent.children = children
    for child in children:
        if not child.decomposition_complete and child.level < max_depth:
            _decompose_children(client=client, dig_id=dig_id, dig_text=dig_text, parent=child, ancestors=ancestors + [child], refs=refs, max_depth=max_depth, max_breadth=max_breadth, cost_tracker=cost_tracker)
