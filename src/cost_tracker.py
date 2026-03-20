import logging

from src.config import MODEL_PRICING
from src.models import CostEntry, CostSummary

logger = logging.getLogger(__name__)


class CostTracker:
    def __init__(self, model: str):
        self.model = model
        self._entries: list[CostEntry] = []
        pricing = MODEL_PRICING.get(model, {})
        self._input_rate = pricing.get("input_per_mtok", 0.0)
        self._output_rate = pricing.get("output_per_mtok", 0.0)
        if not pricing:
            logger.warning(f"No pricing data for model '{model}', cost will show $0.00")

    def record(self, call_type: str, level: int, input_tokens: int, output_tokens: int, actual_cost: float | None = None) -> CostEntry:
        if actual_cost is not None:
            cost = actual_cost
        else:
            cost = (input_tokens * self._input_rate + output_tokens * self._output_rate) / 1_000_000
        entry = CostEntry(
            call_type=call_type, level=level,
            input_tokens=input_tokens, output_tokens=output_tokens, cost_usd=cost,
        )
        self._entries.append(entry)
        source = "actual" if actual_cost is not None else "estimated"
        logger.debug(f"API call: {call_type} L{level} | {input_tokens} in / {output_tokens} out | ${cost:.4f} ({source})")
        return entry

    def get_summary(self) -> CostSummary:
        return CostSummary(breakdown=list(self._entries))

    def format_cost_line(self) -> str:
        s = self.get_summary()
        calls = s.api_calls
        return (
            f"Cost: {calls} API call{'s' if calls != 1 else ''} | "
            f"{s.total_input_tokens:,} input tokens | "
            f"{s.total_output_tokens:,} output tokens | "
            f"${s.total_cost_usd:.4f}"
        )

    def reset(self) -> None:
        self._entries.clear()
