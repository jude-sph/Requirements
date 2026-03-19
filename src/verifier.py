import json
import logging
import time
import anthropic
from src.config import ANTHROPIC_API_KEY, MODEL
from src.cost_tracker import CostTracker
from src.loader import WorkbookData
from src.models import RequirementNode, RequirementTree
from src.prompts import format_vv_prompt

logger = logging.getLogger(__name__)
MAX_RETRIES = 3
RETRY_DELAYS = [1, 2, 4]

def _call_api(client: anthropic.Anthropic, prompt: str, cost_tracker: CostTracker, level: int) -> dict:
    for attempt in range(MAX_RETRIES):
        try:
            resp = client.messages.create(model=MODEL, max_tokens=4096, messages=[{"role": "user", "content": prompt}])
            text = resp.content[0].text
            cost_tracker.record(call_type="vv", level=level, input_tokens=resp.usage.input_tokens, output_tokens=resp.usage.output_tokens)
            if "```json" in text:
                text = text.split("```json")[1].split("```")[0]
            elif "```" in text:
                text = text.split("```")[1].split("```")[0]
            return json.loads(text.strip())
        except (anthropic.APIError, anthropic.APIConnectionError, anthropic.RateLimitError) as e:
            if attempt < MAX_RETRIES - 1:
                delay = RETRY_DELAYS[attempt]
                logger.warning(f"V&V API error (attempt {attempt + 1}): {e}. Retrying in {delay}s...")
                time.sleep(delay)
            else:
                logger.error(f"V&V API call failed after {MAX_RETRIES} attempts: {e}")
                raise
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse V&V JSON: {e}")
            raise

def _format_refs(ref_data: WorkbookData) -> dict:
    return {
        "acceptance_phases": "\n\n".join(ref_data.acceptance_phases),
        "verification_methods": "\n".join(f"- {m['name']}: {m['description']}" for m in ref_data.verification_methods),
        "verification_events": "\n".join(f"- {e['name']}: {e['description']}" for e in ref_data.verification_events),
    }

def apply_vv_to_tree(tree: RequirementTree, ref_data: WorkbookData, cost_tracker: CostTracker) -> None:
    if not tree.root:
        return
    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
    refs = _format_refs(ref_data)

    def _apply_vv(node: RequirementNode) -> None:
        logger.info(f'  Generating V&V for L{node.level}: "{node.technical_requirement[:50]}..."')
        prompt = format_vv_prompt(level=node.level, level_name=node.level_name, technical_requirement=node.technical_requirement, system_hierarchy_id=node.system_hierarchy_id, acceptance_phases=refs["acceptance_phases"], verification_methods=refs["verification_methods"], verification_events=refs["verification_events"])
        try:
            result = _call_api(client, prompt, cost_tracker, node.level)
            node.acceptance_criteria = result.get("acceptance_criteria")
            node.verification_method = result.get("verification_method", [])
            node.verification_event = result.get("verification_event", [])
            node.test_case_descriptions = result.get("test_case_descriptions", [])
            logger.info(f"    V&V: {len(node.verification_method)} method(s)")
        except Exception as e:
            logger.error(f"    V&V failed for L{node.level}: {e}")
        for child in node.children:
            _apply_vv(child)

    _apply_vv(tree.root)
