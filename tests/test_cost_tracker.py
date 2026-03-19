from src.cost_tracker import CostTracker


class TestCostTracker:
    def test_record_and_summarize(self):
        tracker = CostTracker(model="claude-sonnet-4-6")
        tracker.record(call_type="decompose", level=1, input_tokens=3000, output_tokens=600)
        tracker.record(call_type="vv", level=1, input_tokens=2500, output_tokens=500)
        summary = tracker.get_summary()
        assert summary.api_calls == 2
        assert summary.total_input_tokens == 5500
        assert summary.total_output_tokens == 1100
        expected_cost = (5500 * 3.00 + 1100 * 15.00) / 1_000_000
        assert abs(summary.total_cost_usd - expected_cost) < 0.0001

    def test_format_single_dig(self):
        tracker = CostTracker(model="claude-sonnet-4-6")
        tracker.record(call_type="decompose", level=1, input_tokens=3000, output_tokens=600)
        line = tracker.format_cost_line()
        assert "1 API calls" in line or "1 API call" in line
        assert "$" in line

    def test_unknown_model_defaults_to_zero(self):
        tracker = CostTracker(model="unknown-model")
        tracker.record(call_type="decompose", level=1, input_tokens=1000, output_tokens=200)
        summary = tracker.get_summary()
        assert summary.total_cost_usd == 0.0

    def test_reset(self):
        tracker = CostTracker(model="claude-sonnet-4-6")
        tracker.record(call_type="decompose", level=1, input_tokens=3000, output_tokens=600)
        tracker.reset()
        summary = tracker.get_summary()
        assert summary.api_calls == 0
