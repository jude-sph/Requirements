# Requirements Decomposition System Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a Python CLI that decomposes high-level shipbuilding DIGs into multi-level formal requirements using the Claude API.

**Architecture:** Two-phase pipeline per level (decompose + V&V) with depth-first tree traversal. JSON tree as internal model, xlsx export. Structural validation (Python) + semantic judge (LLM). Cost tracking and extensive logging throughout.

**Tech Stack:** Python 3.11+, anthropic SDK, openpyxl, pydantic, python-dotenv, pytest

**Spec:** `docs/superpowers/specs/2026-03-19-requirements-decomposition-design.md`

---

## File Map

| File | Responsibility |
|------|---------------|
| `src/__init__.py` | Package marker |
| `src/models.py` | Pydantic models: RequirementNode, RequirementTree, CostEntry, ValidationResult |
| `src/config.py` | Settings: API key, model, pricing table, file paths, defaults |
| `src/cost_tracker.py` | Token/cost accumulator, per-call logging, summary formatting |
| `src/loader.py` | Read xlsx: DIGs, system hierarchy, chapters, acceptance phases, verification refs |
| `src/prompts.py` | Load prompt templates from `prompts/` dir, format with context |
| `src/decomposer.py` | Level-by-level decomposition LLM calls, tree building |
| `src/verifier.py` | V&V generation LLM calls per requirement node |
| `src/validator.py` | Structural checks (Python) + semantic judge (LLM call) |
| `src/exporter.py` | JSON tree to flattened xlsx export |
| `src/main.py` | CLI entry point: argparse, orchestration, logging setup |
| `prompts/decompose_level.txt` | Decomposition prompt template |
| `prompts/generate_vv.txt` | V&V prompt template |
| `prompts/semantic_judge.txt` | Semantic judge prompt template |
| `prompts/levels_example.txt` | Worked example from levels-example.png |
| `scripts/strip_xlsx.py` | Strip LLM-generated columns from xlsx for testing |
| `tests/test_models.py` | Tests for Pydantic models |
| `tests/test_loader.py` | Tests for xlsx loader |
| `tests/test_cost_tracker.py` | Tests for cost tracking |
| `tests/test_validator.py` | Tests for structural validation |
| `tests/test_exporter.py` | Tests for xlsx export |
| `tests/test_decomposer.py` | Tests for decomposer (mocked API) |
| `tests/test_verifier.py` | Tests for verifier (mocked API) |
| `tests/test_prompts.py` | Tests for prompt loading and formatting |

---

### Task 1: Project Scaffolding

**Files:**
- Create: `requirements.txt`
- Create: `src/__init__.py`
- Create: `.env.example`
- Create: `.gitignore`
- Create: `pytest.ini`

- [ ] **Step 1: Create requirements.txt**

```
anthropic>=0.40.0
openpyxl>=3.1.0
pydantic>=2.0.0
python-dotenv>=1.0.0
pytest>=8.0.0
```

- [ ] **Step 2: Create .env.example**

```
ANTHROPIC_API_KEY=sk-ant-...
MODEL=claude-sonnet-4-6
```

- [ ] **Step 3: Create .gitignore**

```
.env
__pycache__/
*.pyc
output/json/
output/xlsx/
output/logs/
.pytest_cache/
test/
```

- [ ] **Step 4: Create src/__init__.py**

Empty file.

- [ ] **Step 5: Create pytest.ini**

```ini
[pytest]
testpaths = tests
pythonpath = .
```

- [ ] **Step 6: Create output directories**

```bash
mkdir -p output/json output/xlsx output/logs prompts scripts tests
```

- [ ] **Step 7: Install dependencies**

```bash
pip install -r requirements.txt
```

- [ ] **Step 8: Commit**

```bash
git add requirements.txt .env.example .gitignore src/__init__.py pytest.ini
git commit -m "chore: scaffold project structure and dependencies"
```

---

### Task 2: Pydantic Data Models

**Files:**
- Create: `src/models.py`
- Create: `tests/test_models.py`

- [ ] **Step 1: Write failing tests for models**

```python
# tests/test_models.py
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
            level=2,
            level_name="Major System",
            allocation="SDS",
            chapter_code="SDS-Ch 2",
            derived_name="Propulsion",
            technical_requirement="The Propulsion System shall provide power.",
            rationale="Needed for speed.",
            system_hierarchy_id="SBS 200 (Propulsion)",
        )
        parent = RequirementNode(
            level=1,
            level_name="Whole Ship",
            allocation="GTR",
            chapter_code="GTR-Ch 3",
            derived_name="Speed",
            technical_requirement="The Vessel shall achieve 17 knots.",
            rationale="DIG requirement.",
            system_hierarchy_id="SBS 700 (Trials)",
            children=[child],
        )
        assert len(parent.children) == 1
        assert parent.children[0].level == 2

    def test_vv_array_length_mismatch_raises(self):
        with pytest.raises(ValueError):
            RequirementNode(
                level=1,
                level_name="Whole Ship",
                allocation="GTR",
                chapter_code="GTR-Ch 3",
                derived_name="Speed",
                technical_requirement="The Vessel shall achieve 17 knots.",
                rationale="DIG requirement.",
                system_hierarchy_id="SBS 700 (Trials)",
                verification_method=["Analysis", "Test"],
                verification_event=["Design Review"],
                test_case_descriptions=["Review docs."],
            )

    def test_tbd_without_confidence_notes_raises(self):
        with pytest.raises(ValueError):
            RequirementNode(
                level=1,
                level_name="Whole Ship",
                allocation="GTR",
                chapter_code="GTR-Ch 3",
                derived_name="Speed",
                technical_requirement="The Vessel shall provide [TBD] MW.",
                rationale="Reason.",
                system_hierarchy_id="SBS 700 (Trials)",
                confidence_notes=None,
            )

    def test_invalid_allocation_raises(self):
        with pytest.raises(ValueError):
            RequirementNode(
                level=1,
                level_name="Whole Ship",
                allocation="INVALID",
                chapter_code="GTR-Ch 3",
                derived_name="Speed",
                technical_requirement="The Vessel shall do something.",
                rationale="Reason.",
                system_hierarchy_id="SBS 700 (Trials)",
            )


class TestRequirementTree:
    def test_tree_creation(self):
        root = RequirementNode(
            level=1,
            level_name="Whole Ship",
            allocation="GTR",
            chapter_code="GTR-Ch 3",
            derived_name="Speed",
            technical_requirement="The Vessel shall achieve 17 knots.",
            rationale="DIG transposition.",
            system_hierarchy_id="SBS 700 (Trials)",
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
            call_type="decompose",
            level=1,
            input_tokens=3200,
            output_tokens=620,
            cost_usd=0.0189,
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
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
pytest tests/test_models.py -v
```

Expected: FAIL — `ModuleNotFoundError: No module named 'src.models'`

- [ ] **Step 3: Implement models**

```python
# src/models.py
from __future__ import annotations

from pydantic import BaseModel, Field, model_validator


class RequirementNode(BaseModel):
    level: int
    level_name: str
    allocation: str
    chapter_code: str
    derived_name: str
    technical_requirement: str
    rationale: str
    system_hierarchy_id: str
    acceptance_criteria: str | None = None
    verification_method: list[str] = Field(default_factory=list)
    verification_event: list[str] = Field(default_factory=list)
    test_case_descriptions: list[str] = Field(default_factory=list)
    confidence_notes: str | None = None
    decomposition_complete: bool = False
    children: list[RequirementNode] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_vv_arrays(self) -> RequirementNode:
        methods = self.verification_method
        events = self.verification_event
        cases = self.test_case_descriptions
        lengths = [len(methods), len(events), len(cases)]
        non_zero = [l for l in lengths if l > 0]
        if non_zero and len(set(non_zero)) > 1:
            raise ValueError(
                f"V&V array length mismatch: methods={len(methods)}, "
                f"events={len(events)}, test_cases={len(cases)}"
            )
        return self

    @model_validator(mode="after")
    def validate_tbd_has_notes(self) -> RequirementNode:
        if "[TBD]" in self.technical_requirement and not self.confidence_notes:
            raise ValueError(
                "technical_requirement contains [TBD] but confidence_notes is empty"
            )
        return self

    @model_validator(mode="after")
    def validate_allocation(self) -> RequirementNode:
        valid = {"GTR", "SDS", "GTR / SDS"}
        if self.allocation not in valid:
            raise ValueError(f"Invalid allocation '{self.allocation}', must be one of {valid}")
        return self


class RequirementTree(BaseModel):
    dig_id: str
    dig_text: str
    root: RequirementNode | None = None
    validation: ValidationResult | None = None
    cost: CostSummary | None = None

    def count_nodes(self) -> int:
        if not self.root:
            return 0

        def _count(node: RequirementNode) -> int:
            return 1 + sum(_count(c) for c in node.children)

        return _count(self.root)

    def max_depth(self) -> int:
        if not self.root:
            return 0

        def _depth(node: RequirementNode) -> int:
            if not node.children:
                return 1
            return 1 + max(_depth(c) for c in node.children)

        return _depth(self.root)


class CostEntry(BaseModel):
    call_type: str  # "decompose", "vv", "judge"
    level: int
    input_tokens: int
    output_tokens: int
    cost_usd: float


class CostSummary(BaseModel):
    breakdown: list[CostEntry] = Field(default_factory=list)

    @property
    def total_input_tokens(self) -> int:
        return sum(e.input_tokens for e in self.breakdown)

    @property
    def total_output_tokens(self) -> int:
        return sum(e.output_tokens for e in self.breakdown)

    @property
    def total_cost_usd(self) -> float:
        return sum(e.cost_usd for e in self.breakdown)

    @property
    def api_calls(self) -> int:
        return len(self.breakdown)


class ValidationIssue(BaseModel):
    severity: str  # "error" or "warning"
    message: str
    node_path: str  # e.g. "L1 > L2.1 > L3.1"


class ValidationResult(BaseModel):
    structural_errors: list[ValidationIssue] = Field(default_factory=list)
    semantic_review: SemanticReview | None = None


class SemanticReview(BaseModel):
    status: str  # "pass" or "flag"
    issues: list[ValidationIssue] = Field(default_factory=list)
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
pytest tests/test_models.py -v
```

Expected: All PASS

- [ ] **Step 5: Commit**

```bash
git add src/models.py tests/test_models.py
git commit -m "feat: add Pydantic data models for requirement tree, cost, validation"
```

---

### Task 3: Configuration

**Files:**
- Create: `src/config.py`

- [ ] **Step 1: Create config.py**

```python
# src/config.py
import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

# Paths
PROJECT_ROOT = Path(__file__).parent.parent
XLSX_PATH = PROJECT_ROOT / "GTR-SDS.xlsx"
PROMPTS_DIR = PROJECT_ROOT / "prompts"
OUTPUT_JSON_DIR = PROJECT_ROOT / "output" / "json"
OUTPUT_XLSX_DIR = PROJECT_ROOT / "output" / "xlsx"
OUTPUT_LOGS_DIR = PROJECT_ROOT / "output" / "logs"

# API
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")
MODEL = os.getenv("MODEL", "claude-sonnet-4-6")

# Defaults
DEFAULT_MAX_DEPTH = 4
DEFAULT_MAX_BREADTH = 3

# Pricing (USD per million tokens)
MODEL_PRICING = {
    "claude-sonnet-4-6": {"input_per_mtok": 3.00, "output_per_mtok": 15.00},
    "claude-opus-4-6": {"input_per_mtok": 15.00, "output_per_mtok": 75.00},
    "claude-haiku-4-5": {"input_per_mtok": 0.80, "output_per_mtok": 4.00},
}

# Level names
LEVEL_NAMES = {
    1: "Whole Ship",
    2: "Major System",
    3: "Subsystem",
    4: "Equipment",
}
```

- [ ] **Step 2: Commit**

```bash
git add src/config.py
git commit -m "feat: add configuration with API, paths, pricing, defaults"
```

---

### Task 4: Cost Tracker

**Files:**
- Create: `src/cost_tracker.py`
- Create: `tests/test_cost_tracker.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/test_cost_tracker.py
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
        # sonnet: $3/Mtok input, $15/Mtok output
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
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
pytest tests/test_cost_tracker.py -v
```

Expected: FAIL — `ModuleNotFoundError`

- [ ] **Step 3: Implement cost_tracker.py**

```python
# src/cost_tracker.py
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

    def record(self, call_type: str, level: int, input_tokens: int, output_tokens: int) -> CostEntry:
        cost = (input_tokens * self._input_rate + output_tokens * self._output_rate) / 1_000_000
        entry = CostEntry(
            call_type=call_type,
            level=level,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            cost_usd=cost,
        )
        self._entries.append(entry)
        logger.debug(
            f"API call: {call_type} L{level} | "
            f"{input_tokens} in / {output_tokens} out | ${cost:.4f}"
        )
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
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
pytest tests/test_cost_tracker.py -v
```

Expected: All PASS

- [ ] **Step 5: Commit**

```bash
git add src/cost_tracker.py tests/test_cost_tracker.py
git commit -m "feat: add cost tracker with per-call recording and summary formatting"
```

---

### Task 5: XLSX Loader

**Files:**
- Create: `src/loader.py`
- Create: `tests/test_loader.py`

This is one of the trickiest parts. The xlsx has many data quality issues: phantom rows, float DNG IDs, leading whitespace, multi-row entries, comma-separated lists.

- [ ] **Step 1: Write failing tests**

```python
# tests/test_loader.py
import pytest
from pathlib import Path
from src.loader import load_workbook_data

XLSX_PATH = Path(__file__).parent.parent / "GTR-SDS.xlsx"


@pytest.fixture(scope="module")
def data():
    return load_workbook_data(XLSX_PATH)


class TestLoadDigs:
    def test_digs_loaded(self, data):
        assert len(data.digs) > 100
        assert len(data.digs) <= 110  # 109 expected, minus duplicates

    def test_dig_has_id_and_text(self, data):
        first = list(data.digs.values())[0]
        assert first["dig_id"] != ""
        assert first["dig_text"] != ""
        # DNG should be a string of digits, not float
        assert "." not in first["dig_id"]

    def test_no_leading_whitespace_in_dig_text(self, data):
        for dig in data.digs.values():
            assert dig["dig_text"] == dig["dig_text"].strip()

    def test_duplicate_dig_warned(self, data, capfd):
        # DIG 10237 appears twice; loader should use first occurrence
        assert "10237" in data.digs


class TestLoadSystemHierarchy:
    def test_hierarchy_loaded(self, data):
        assert len(data.system_hierarchy) > 100

    def test_top_level_blocks(self, data):
        ids = [h["id"] for h in data.system_hierarchy]
        assert any("100" in id for id in ids)
        assert any("200" in id for id in ids)
        assert any("900" in id for id in ids)

    def test_no_empty_entries(self, data):
        for h in data.system_hierarchy:
            assert h["id"].strip() != ""


class TestLoadChapters:
    def test_gtr_chapters_loaded(self, data):
        assert len(data.gtr_chapters) >= 11

    def test_sds_chapters_loaded(self, data):
        assert len(data.sds_chapters) >= 20

    def test_chapter_codes_stripped(self, data):
        for ch in data.gtr_chapters:
            assert ch == ch.strip()
        for ch in data.sds_chapters:
            assert ch == ch.strip()

    def test_gtr_chapter_format(self, data):
        for ch in data.gtr_chapters:
            assert ch.startswith("GTR-Ch")


class TestLoadAcceptancePhases:
    def test_five_phases(self, data):
        assert len(data.acceptance_phases) == 5

    def test_phase_text_not_empty(self, data):
        for phase in data.acceptance_phases:
            assert len(phase) > 20


class TestLoadVerificationRefs:
    def test_methods_loaded(self, data):
        assert len(data.verification_methods) >= 5
        method_names = [m["name"] for m in data.verification_methods]
        assert any("Test" in n for n in method_names)
        assert any("Inspection" in n for n in method_names)

    def test_events_loaded(self, data):
        assert len(data.verification_events) >= 6
        event_names = [e["name"] for e in data.verification_events]
        assert any("FAT" in n for n in event_names)
        assert any("HAT" in n for n in event_names)
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
pytest tests/test_loader.py -v
```

Expected: FAIL — `ModuleNotFoundError`

- [ ] **Step 3: Implement loader.py**

```python
# src/loader.py
import logging
import re
from dataclasses import dataclass, field
from pathlib import Path

from openpyxl import load_workbook

logger = logging.getLogger(__name__)


def _strip(val) -> str:
    """Convert cell value to stripped string. Handle None, floats, non-breaking spaces."""
    if val is None:
        return ""
    s = str(val).strip()
    s = s.replace("\xa0", " ")  # non-breaking space
    return s


@dataclass
class WorkbookData:
    digs: dict[str, dict] = field(default_factory=dict)  # dig_id -> {"dig_id", "dig_text"}
    system_hierarchy: list[dict] = field(default_factory=list)  # [{"id": "100 Hull..."}]
    gtr_chapters: list[str] = field(default_factory=list)  # ["GTR-Ch 1: ...", ...]
    sds_chapters: list[str] = field(default_factory=list)
    acceptance_phases: list[str] = field(default_factory=list)
    verification_methods: list[dict] = field(default_factory=list)  # [{"name", "description"}]
    verification_events: list[dict] = field(default_factory=list)


def load_workbook_data(xlsx_path: Path) -> WorkbookData:
    logger.info(f"Loading workbook: {xlsx_path}")
    wb = load_workbook(xlsx_path, read_only=True, data_only=True)
    data = WorkbookData()

    _load_digs(wb["Requirements Decomposition"], data)
    _load_system_hierarchy(wb["System Hierarchy"], data)
    _load_chapters(wb["GTR Chapters"], data.gtr_chapters, prefix="GTR-Ch")
    _load_chapters(wb["SDS Chapters"], data.sds_chapters, prefix="SDS-Ch")
    _load_acceptance_phases(wb, data)
    _load_verification_methods(wb["Verification Events"], data)  # sheet name is misleading
    _load_verification_events(wb["Verification Means"], data)  # sheet name is misleading

    wb.close()
    logger.info(
        f"Loaded: {len(data.digs)} DIGs, {len(data.system_hierarchy)} hierarchy entries, "
        f"{len(data.gtr_chapters)} GTR chapters, {len(data.sds_chapters)} SDS chapters, "
        f"{len(data.acceptance_phases)} phases, {len(data.verification_methods)} methods, "
        f"{len(data.verification_events)} events"
    )
    return data


def _load_digs(ws, data: WorkbookData) -> None:
    seen_ids = set()
    for i, row in enumerate(ws.iter_rows(min_row=2, values_only=True), start=2):
        if row[0] is None:
            continue
        # DNG column is float (e.g. 9584.0), convert to int string
        dig_id = str(int(float(row[0])))
        dig_text = _strip(row[1])
        if not dig_text:
            continue
        if dig_id in seen_ids:
            logger.warning(f"Duplicate DIG ID {dig_id} at row {i}, skipping")
            continue
        seen_ids.add(dig_id)
        data.digs[dig_id] = {"dig_id": dig_id, "dig_text": dig_text}
    logger.info(f"  Loaded {len(data.digs)} unique DIGs")


def _load_system_hierarchy(ws, data: WorkbookData) -> None:
    for row in ws.iter_rows(min_row=2, values_only=True):
        val = _strip(row[0])
        if val:
            data.system_hierarchy.append({"id": val})


def _load_chapters(ws, chapter_list: list[str], prefix: str) -> None:
    for row in ws.iter_rows(min_row=2, values_only=True):
        val = _strip(row[0])
        if val and val.startswith(prefix):
            chapter_list.append(val)


def _load_acceptance_phases(wb, data: WorkbookData) -> None:
    ws = wb["Acceptance Phases"]
    # Phase 1 is in the header cell (A1), phases 2-5 in rows 2-5
    for row in ws.iter_rows(min_row=1, values_only=True):
        val = _strip(row[0])
        if val and "Acceptance Phase" in val:
            data.acceptance_phases.append(val)


def _load_verification_methods(ws, data: WorkbookData) -> None:
    """Load from 'Verification Events' sheet (which actually contains methods)."""
    for row in ws.iter_rows(min_row=2, values_only=True):
        name = _strip(row[0])
        desc = _strip(row[1]) if len(row) > 1 else ""
        if name:
            data.verification_methods.append({"name": name, "description": desc})


def _load_verification_events(ws, data: WorkbookData) -> None:
    """Load from 'Verification Means' sheet (which actually contains events).
    Multi-row entries: continuation rows have None in col A; forward-fill."""
    current_name = ""
    current_desc = ""
    for row in ws.iter_rows(min_row=2, values_only=True):
        name = _strip(row[0])
        desc = _strip(row[1]) if len(row) > 1 else ""
        if name:
            # Save previous entry
            if current_name:
                data.verification_events.append(
                    {"name": current_name, "description": current_desc}
                )
            current_name = name
            current_desc = desc
        elif current_name and desc:
            # Continuation row
            current_desc += " " + desc
    # Save last entry
    if current_name:
        data.verification_events.append(
            {"name": current_name, "description": current_desc}
        )
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
pytest tests/test_loader.py -v
```

Expected: All PASS

- [ ] **Step 5: Commit**

```bash
git add src/loader.py tests/test_loader.py
git commit -m "feat: add xlsx loader with data cleaning, duplicate handling, and ref data"
```

---

### Task 6: Prompt Templates

**Files:**
- Create: `prompts/levels_example.txt`
- Create: `prompts/decompose_level.txt`
- Create: `prompts/generate_vv.txt`
- Create: `prompts/semantic_judge.txt`
- Create: `src/prompts.py`

- [ ] **Step 1: Create levels_example.txt**

```
# Decomposition Levels Example

## Level 1: Whole Ship
- SBS/Chapter: SBS 700 (Trials) / SDS-Ch 1
- Technical Requirement: "The Vessel shall achieve a maximum attainable forward speed of at least 17 knots when operating at Design Draft in WMO Sea State 1 with a clean hull."
- Rationale: "Direct transposition of DIG [9646] into a verifiable top-level performance requirement."

## Level 2: Major System
- SBS/Chapter: SBS 200 (Propulsion) / SDS-Ch 2
- Technical Requirement: "The Propulsion System shall provide a minimum delivered power (SP, dB) of [X] MW to the propulsors to overcome total hull resistance at 17 knots."
- Rationale: "Defines the power-to-speed relationship required to meet the Level 1 mission objective."

## Level 3: Subsystem
- SBS/Chapter: SBS 234 (Podded Propulsors) / SDS-Ch 4
- Technical Requirement: "Each Azimuthing Podded Propulsor shall be rated for a continuous output of [Y] kW at [Z] RPM in open water conditions."
- Rationale: "Allocates the total required power (SP, dB) across the individual propulsion units."

## Level 4: Equipment
- SBS/Chapter: SBS 231 (Propulsion Motors) / GTR-Ch 12
- Technical Requirement: "The Propulsion Motor shall maintain a winding temperature not exceeding 120°C during 4 hours of continuous operation at 100% MCR (Maximum Continuous Rating)."
- Rationale: "Provides a verifiable hardware constraint (900/GTR-12 Quality) to ensure the motor can safely sustain the speed required."
```

- [ ] **Step 2: Create decompose_level.txt**

```
You are a naval systems engineer performing requirements decomposition per ISO 15288 for a Canadian Coast Guard Polar Icebreaker.

Your task: Derive the Level {target_level} ({target_level_name}) child requirements from the parent requirement below. You are decomposing from {parent_scope} scope to {child_scope} scope.

Return between 1 and {max_breadth} child requirements. Only create multiple children when the parent genuinely implies distinct system-level concerns. Do not force breadth.

## Source DIG
DIG ID: {dig_id}
DIG Text: {dig_text}

## Parent Chain (for context)
{parent_chain}

## Reference: System Hierarchy
{system_hierarchy}

## Reference: Chapter Structure
{chapter_list}

## Worked Example
{levels_example}

## Output Format
Return a JSON object with this exact structure:
{{
  "children": [
    {{
      "level": {target_level},
      "level_name": "{target_level_name}",
      "allocation": "GTR or SDS or GTR / SDS",
      "chapter_code": "chapter code from reference above",
      "derived_name": "short descriptive title",
      "technical_requirement": "The [System] shall ... (IEEE 29481 format)",
      "rationale": "why this requirement is needed and how it satisfies the parent",
      "system_hierarchy_id": "SBS ID from hierarchy reference above",
      "confidence_notes": "explain any [TBD] values, or null if all values are concrete",
      "decomposition_complete": false
    }}
  ],
  "decomposition_complete": false
}}

If further decomposition at this level is not meaningful (e.g. the parent is a policy requirement with no {child_scope}-level mapping), set the top-level "decomposition_complete" to true and return an empty children array.

## Rules
- Every technical_requirement MUST use IEEE 29481 "shall" format: "The [System] shall..."
- Do NOT add features or capabilities not mentioned or implied by the DIG
- Use [TBD] with a confidence_notes explanation when specific values cannot be derived from the source DIG
- Use concrete values from the DIG wherever available
- allocation: "GTR" for whole-vessel concerns, "SDS" for system-specific, "GTR / SDS" for both
- chapter_code must be from the chapter reference provided above
- system_hierarchy_id must be from the system hierarchy reference provided above
- If you cannot determine a chapter or system ID, use "Information Not Found"
```

- [ ] **Step 3: Create generate_vv.txt**

```
You are a verification and validation engineer for a Canadian Coast Guard Polar Icebreaker project.

Your task: Generate V&V data for the following technical requirement, maximising early verification coverage across all 5 acceptance phases.

## Technical Requirement
Level: {level} ({level_name})
Requirement: {technical_requirement}
System: {system_hierarchy_id}

## Reference: Acceptance Phases
{acceptance_phases}

## Reference: Verification Methods
{verification_methods}

## Reference: Verification Events
{verification_events}

## Output Format
Return a JSON object with this exact structure:
{{
  "acceptance_criteria": "A paragraph describing how the requirement is progressively verified across the 5 phases, from design through final acceptance.",
  "verification_method": ["method1", "method2"],
  "verification_event": ["event1", "event2"],
  "test_case_descriptions": ["description for method1/event1 pair", "description for method2/event2 pair"]
}}

## Rules
- verification_method entries must be from: Test, Inspection, Demonstration, Analysis, Review, 3rd Party Cert
- verification_event entries must be from: Design Disclosure, FAT, HAT, SAT, Customer Sea Trials, Third Party Certification
- verification_method, verification_event, and test_case_descriptions arrays MUST have the same length
- Each test_case_description must be specific to its corresponding method/event pair
- Include as much early verification coverage as feasible (don't defer everything to sea trials)
- Each test_case_description should be a single paragraph describing the technical approach
```

- [ ] **Step 4: Create semantic_judge.txt**

```
You are an independent requirements reviewer auditing a decomposition tree for a Canadian Coast Guard Polar Icebreaker project. Your job is to find problems.

Review the following requirement tree that was decomposed from a single DIG (Design Instruction and Guideline).

## Source DIG
DIG ID: {dig_id}
DIG Text: {dig_text}

## Requirement Tree
{tree_json}

## Review Checklist
For each parent-child relationship in the tree:
1. Does the child requirement genuinely refine or decompose its parent? (not just reword it)
2. Is the system hierarchy allocation appropriate for the level? (Level 1 = whole ship, Level 2 = major system, etc.)
3. Is the chapter code allocation correct? (GTR for whole-vessel, SDS for system-specific)
4. Are [TBD] placeholders justified with adequate confidence_notes? (not lazy omissions)
5. Is the level of specificity appropriate? (not too abstract for the level, not too detailed)
6. Do the verification methods make sense for the requirement type?
7. Are verification events appropriate for the acceptance phase?
8. Does each test case description match its corresponding method/event pair?

## Output Format
Return a JSON object:
{{
  "status": "pass" or "flag",
  "issues": [
    {{
      "severity": "error" or "warning",
      "message": "description of the issue",
      "node_path": "L1 > L2.1 > L3.1 (path to the problematic node)"
    }}
  ]
}}

If no issues found, return {{"status": "pass", "issues": []}}.

Be thorough but fair. Only flag genuine problems, not stylistic preferences.
```

- [ ] **Step 5: Implement prompts.py**

```python
# src/prompts.py
import logging
from pathlib import Path

from src.config import PROMPTS_DIR

logger = logging.getLogger(__name__)

_cache: dict[str, str] = {}


def _load_template(name: str) -> str:
    if name not in _cache:
        path = PROMPTS_DIR / name
        logger.debug(f"Loading prompt template: {path}")
        _cache[name] = path.read_text()
    return _cache[name]


def format_decompose_prompt(
    dig_id: str,
    dig_text: str,
    target_level: int,
    target_level_name: str,
    parent_scope: str,
    child_scope: str,
    parent_chain: str,
    system_hierarchy: str,
    chapter_list: str,
    max_breadth: int,
) -> str:
    template = _load_template("decompose_level.txt")
    levels_example = _load_template("levels_example.txt")
    return template.format(
        dig_id=dig_id,
        dig_text=dig_text,
        target_level=target_level,
        target_level_name=target_level_name,
        parent_scope=parent_scope,
        child_scope=child_scope,
        parent_chain=parent_chain,
        system_hierarchy=system_hierarchy,
        chapter_list=chapter_list,
        levels_example=levels_example,
        max_breadth=max_breadth,
    )


def format_vv_prompt(
    level: int,
    level_name: str,
    technical_requirement: str,
    system_hierarchy_id: str,
    acceptance_phases: str,
    verification_methods: str,
    verification_events: str,
) -> str:
    template = _load_template("generate_vv.txt")
    return template.format(
        level=level,
        level_name=level_name,
        technical_requirement=technical_requirement,
        system_hierarchy_id=system_hierarchy_id,
        acceptance_phases=acceptance_phases,
        verification_methods=verification_methods,
        verification_events=verification_events,
    )


def format_judge_prompt(dig_id: str, dig_text: str, tree_json: str) -> str:
    template = _load_template("semantic_judge.txt")
    return template.format(
        dig_id=dig_id,
        dig_text=dig_text,
        tree_json=tree_json,
    )
```

- [ ] **Step 6: Commit**

```bash
git add prompts/ src/prompts.py
git commit -m "feat: add prompt templates and prompt formatting module"
```

---

### Task 7: Decomposer

**Files:**
- Create: `src/decomposer.py`
- Create: `tests/test_decomposer.py`

- [ ] **Step 1: Write failing tests (mocked API)**

```python
# tests/test_decomposer.py
import json
from unittest.mock import MagicMock, patch

import pytest

from src.cost_tracker import CostTracker
from src.decomposer import decompose_dig
from src.loader import WorkbookData


def _make_mock_response(content: dict, input_tokens=1000, output_tokens=500):
    """Create a mock Anthropic API response."""
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
    # Mock returns 1 child at L1, then decomposition_complete at L2
    l1_response = _make_mock_response({
        "children": [{
            "level": 1,
            "level_name": "Whole Ship",
            "allocation": "GTR",
            "chapter_code": "GTR-Ch 3: Whole Ship Performance",
            "derived_name": "Maximum Speed",
            "technical_requirement": "The Vessel shall achieve 17 knots.",
            "rationale": "DIG transposition.",
            "system_hierarchy_id": "SBS 700 (Trials)",
            "confidence_notes": None,
            "decomposition_complete": False,
        }],
        "decomposition_complete": False,
    })
    l2_response = _make_mock_response({
        "children": [],
        "decomposition_complete": True,
    })

    mock_client = MagicMock()
    mock_client.messages.create.side_effect = [l1_response, l2_response]
    mock_anthropic.Anthropic.return_value = mock_client

    tracker = CostTracker(model="claude-sonnet-4-6")
    tree = decompose_dig(
        dig_id="9584",
        dig_text="The ship must do 17 knots.",
        ref_data=ref_data,
        max_depth=2,
        max_breadth=3,
        skip_vv=True,
        cost_tracker=tracker,
    )
    assert tree.root is not None
    assert tree.root.level == 1
    assert tree.root.technical_requirement == "The Vessel shall achieve 17 knots."
    assert tree.count_nodes() == 1  # only L1, L2 was decomposition_complete
    assert tracker.get_summary().api_calls == 2  # L1 decompose + L2 decompose (returned empty)


@patch("src.decomposer.anthropic")
def test_max_depth_respected(mock_anthropic, ref_data):
    # Always returns children, but max_depth=1 should stop after L1
    l1_response = _make_mock_response({
        "children": [{
            "level": 1,
            "level_name": "Whole Ship",
            "allocation": "GTR",
            "chapter_code": "GTR-Ch 3: Whole Ship Performance",
            "derived_name": "Speed",
            "technical_requirement": "The Vessel shall do things.",
            "rationale": "Reason.",
            "system_hierarchy_id": "SBS 700 (Trials)",
            "confidence_notes": None,
            "decomposition_complete": False,
        }],
        "decomposition_complete": False,
    })

    mock_client = MagicMock()
    mock_client.messages.create.return_value = l1_response
    mock_anthropic.Anthropic.return_value = mock_client

    tracker = CostTracker(model="claude-sonnet-4-6")
    tree = decompose_dig(
        dig_id="9584",
        dig_text="The ship must do stuff.",
        ref_data=ref_data,
        max_depth=1,
        max_breadth=3,
        skip_vv=True,
        cost_tracker=tracker,
    )
    assert tree.root is not None
    assert tree.max_depth() == 1  # stopped at L1
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
pytest tests/test_decomposer.py -v
```

Expected: FAIL — `ModuleNotFoundError`

- [ ] **Step 3: Implement decomposer.py**

```python
# src/decomposer.py
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
    """Make an API call with retry logic. Returns parsed JSON dict."""
    for attempt in range(MAX_RETRIES):
        try:
            logger.debug(f"API call: {call_type} L{level} (attempt {attempt + 1})")
            logger.debug(f"Prompt length: {len(prompt)} chars")

            resp = client.messages.create(
                model=MODEL,
                max_tokens=4096,
                messages=[{"role": "user", "content": prompt}],
            )

            text = resp.content[0].text
            logger.debug(f"Response length: {len(text)} chars")

            cost_tracker.record(
                call_type=call_type,
                level=level,
                input_tokens=resp.usage.input_tokens,
                output_tokens=resp.usage.output_tokens,
            )

            # Extract JSON from response (handle markdown code blocks)
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
    """Format reference data as strings for prompt injection."""
    hierarchy_str = "\n".join(h["id"] for h in ref_data.system_hierarchy)
    gtr_str = "\n".join(ref_data.gtr_chapters)
    sds_str = "\n".join(ref_data.sds_chapters)
    phases_str = "\n\n".join(ref_data.acceptance_phases)
    methods_str = "\n".join(f"- {m['name']}: {m['description']}" for m in ref_data.verification_methods)
    events_str = "\n".join(f"- {e['name']}: {e['description']}" for e in ref_data.verification_events)
    return {
        "system_hierarchy": hierarchy_str,
        "gtr_chapters": gtr_str,
        "sds_chapters": sds_str,
        "all_chapters": f"### GTR Chapters\n{gtr_str}\n\n### SDS Chapters\n{sds_str}",
        "acceptance_phases": phases_str,
        "verification_methods": methods_str,
        "verification_events": events_str,
    }


def _build_parent_chain(ancestors: list[RequirementNode]) -> str:
    """Format ancestor chain as context string."""
    if not ancestors:
        return "(This is the first level — no parent requirements yet.)"
    lines = []
    for node in ancestors:
        lines.append(
            f"Level {node.level} ({node.level_name}):\n"
            f"  Requirement: {node.technical_requirement}\n"
            f"  Allocation: {node.allocation}\n"
            f"  System: {node.system_hierarchy_id}\n"
            f"  Chapter: {node.chapter_code}"
        )
    return "\n\n".join(lines)


def decompose_dig(
    dig_id: str,
    dig_text: str,
    ref_data: WorkbookData,
    max_depth: int,
    max_breadth: int,
    skip_vv: bool,
    cost_tracker: CostTracker,
) -> RequirementTree:
    """Decompose a single DIG into a requirement tree."""
    logger.info(f"Decomposing DIG {dig_id}: \"{dig_text[:80]}...\"")

    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
    refs = _format_ref_data(ref_data)
    tree = RequirementTree(dig_id=dig_id, dig_text=dig_text)

    # Decompose Level 1 (root)
    root_children = _decompose_level(
        client=client,
        dig_id=dig_id,
        dig_text=dig_text,
        target_level=1,
        ancestors=[],
        refs=refs,
        max_breadth=max_breadth,
        cost_tracker=cost_tracker,
    )

    if not root_children:
        logger.warning(f"DIG {dig_id}: No Level 1 requirements generated")
        return tree

    # Use first child as root (Level 1 always has exactly 1 node)
    root = root_children[0]
    tree.root = root

    # Recursively decompose children
    if max_depth > 1:
        _decompose_children(
            client=client,
            dig_id=dig_id,
            dig_text=dig_text,
            parent=root,
            ancestors=[root],
            refs=refs,
            max_depth=max_depth,
            max_breadth=max_breadth,
            cost_tracker=cost_tracker,
        )

    return tree


def _decompose_level(
    client: anthropic.Anthropic,
    dig_id: str,
    dig_text: str,
    target_level: int,
    ancestors: list[RequirementNode],
    refs: dict,
    max_breadth: int,
    cost_tracker: CostTracker,
) -> list[RequirementNode]:
    """Make one decomposition API call. Returns list of child RequirementNodes."""
    target_name = LEVEL_NAMES.get(target_level, f"Level {target_level}")
    parent_name = LEVEL_NAMES.get(target_level - 1, "DIG") if target_level > 1 else "DIG"

    prompt = format_decompose_prompt(
        dig_id=dig_id,
        dig_text=dig_text,
        target_level=target_level,
        target_level_name=target_name,
        parent_scope=parent_name,
        child_scope=target_name,
        parent_chain=_build_parent_chain(ancestors),
        system_hierarchy=refs["system_hierarchy"],
        chapter_list=refs["all_chapters"],
        max_breadth=max_breadth,
    )

    result = _call_api(client, prompt, cost_tracker, "decompose", target_level)

    if result.get("decomposition_complete", False):
        logger.info(f"  L{target_level}: Decomposition complete (no further breakdown)")
        return []

    children = []
    for child_data in result.get("children", [])[:max_breadth]:
        try:
            node = RequirementNode(
                level=child_data.get("level", target_level),
                level_name=child_data.get("level_name", target_name),
                allocation=child_data.get("allocation", "Information Not Found"),
                chapter_code=child_data.get("chapter_code", "Information Not Found"),
                derived_name=child_data.get("derived_name", ""),
                technical_requirement=child_data.get("technical_requirement", ""),
                rationale=child_data.get("rationale", ""),
                system_hierarchy_id=child_data.get("system_hierarchy_id", "Information Not Found"),
                confidence_notes=child_data.get("confidence_notes"),
                decomposition_complete=child_data.get("decomposition_complete", False),
            )
            children.append(node)
            logger.info(f"  L{target_level} ({node.allocation}): \"{node.technical_requirement[:60]}...\"")
        except Exception as e:
            logger.error(f"  L{target_level}: Failed to parse child: {e}")

    return children


def _decompose_children(
    client: anthropic.Anthropic,
    dig_id: str,
    dig_text: str,
    parent: RequirementNode,
    ancestors: list[RequirementNode],
    refs: dict,
    max_depth: int,
    max_breadth: int,
    cost_tracker: CostTracker,
) -> None:
    """Recursively decompose children of a node (depth-first)."""
    if parent.level >= max_depth:
        return
    if parent.decomposition_complete:
        return

    children = _decompose_level(
        client=client,
        dig_id=dig_id,
        dig_text=dig_text,
        target_level=parent.level + 1,
        ancestors=ancestors,
        refs=refs,
        max_breadth=max_breadth,
        cost_tracker=cost_tracker,
    )

    parent.children = children

    for child in children:
        if not child.decomposition_complete and child.level < max_depth:
            _decompose_children(
                client=client,
                dig_id=dig_id,
                dig_text=dig_text,
                parent=child,
                ancestors=ancestors + [child],
                refs=refs,
                max_depth=max_depth,
                max_breadth=max_breadth,
                cost_tracker=cost_tracker,
            )
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
pytest tests/test_decomposer.py -v
```

Expected: All PASS

- [ ] **Step 5: Commit**

```bash
git add src/decomposer.py tests/test_decomposer.py
git commit -m "feat: add decomposer with depth-first tree traversal and retry logic"
```

---

### Task 8: V&V Verifier

**Files:**
- Create: `src/verifier.py`
- Create: `tests/test_verifier.py`

- [ ] **Step 1: Write failing tests (mocked API)**

```python
# tests/test_verifier.py
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
    child = RequirementNode(
        level=2, level_name="Major System", allocation="SDS",
        chapter_code="SDS-Ch 2", derived_name="Propulsion",
        technical_requirement="The Propulsion System shall provide power.",
        rationale="R.", system_hierarchy_id="SBS 200",
    )
    root = RequirementNode(
        level=1, level_name="Whole Ship", allocation="GTR",
        chapter_code="GTR-Ch 3", derived_name="Speed",
        technical_requirement="The Vessel shall achieve 17 knots.",
        rationale="R.", system_hierarchy_id="SBS 700",
        children=[child],
    )
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
    assert tracker.get_summary().api_calls == 2  # one per node
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
pytest tests/test_verifier.py -v
```

Expected: FAIL

- [ ] **Step 3: Implement verifier.py**

```python
# src/verifier.py
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
            resp = client.messages.create(
                model=MODEL,
                max_tokens=4096,
                messages=[{"role": "user", "content": prompt}],
            )
            text = resp.content[0].text
            cost_tracker.record(
                call_type="vv", level=level,
                input_tokens=resp.usage.input_tokens,
                output_tokens=resp.usage.output_tokens,
            )
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
        "verification_methods": "\n".join(
            f"- {m['name']}: {m['description']}" for m in ref_data.verification_methods
        ),
        "verification_events": "\n".join(
            f"- {e['name']}: {e['description']}" for e in ref_data.verification_events
        ),
    }


def apply_vv_to_tree(tree: RequirementTree, ref_data: WorkbookData, cost_tracker: CostTracker) -> None:
    """Walk the tree and apply V&V data to every node."""
    if not tree.root:
        return

    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
    refs = _format_refs(ref_data)

    def _apply_vv(node: RequirementNode) -> None:
        logger.info(f"  Generating V&V for L{node.level}: \"{node.technical_requirement[:50]}...\"")

        prompt = format_vv_prompt(
            level=node.level,
            level_name=node.level_name,
            technical_requirement=node.technical_requirement,
            system_hierarchy_id=node.system_hierarchy_id,
            acceptance_phases=refs["acceptance_phases"],
            verification_methods=refs["verification_methods"],
            verification_events=refs["verification_events"],
        )

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
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
pytest tests/test_verifier.py -v
```

Expected: All PASS

- [ ] **Step 5: Commit**

```bash
git add src/verifier.py tests/test_verifier.py
git commit -m "feat: add V&V verifier with tree traversal and API retry"
```

---

### Task 9: Structural Validator

**Files:**
- Create: `src/validator.py`
- Create: `tests/test_validator.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/test_validator.py
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
        test_case_descriptions=["Review design."],
    )
    root = RequirementNode(
        level=1, level_name="Whole Ship", allocation="GTR",
        chapter_code="GTR-Ch 3: Whole Ship Performance", derived_name="Speed",
        technical_requirement="The Vessel shall achieve 17 knots.",
        rationale="R.", system_hierarchy_id="SBS 700 (Trials)",
        verification_method=["Test"], verification_event=["Sea Trials"],
        test_case_descriptions=["Run speed trial."],
        children=[child],
    )
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
        tree.root.verification_event = ["Sea Trials"]  # mismatch
        errors = validate_tree_structure(tree, ref_data, max_depth=4, max_breadth=3)
        assert any("mismatch" in e.message.lower() or "length" in e.message.lower() for e in errors)

    def test_child_level_not_parent_plus_one(self, ref_data):
        tree = _make_valid_tree()
        tree.root.children[0].level = 5  # should be 2
        errors = validate_tree_structure(tree, ref_data, max_depth=4, max_breadth=3)
        assert any("level" in e.message.lower() for e in errors)

    def test_exceeds_max_depth(self, ref_data):
        tree = _make_valid_tree()
        errors = validate_tree_structure(tree, ref_data, max_depth=1, max_breadth=3)
        assert any("depth" in e.message.lower() for e in errors)

    def test_exceeds_max_breadth(self, ref_data):
        tree = _make_valid_tree()
        # Add extra children to root
        for i in range(5):
            tree.root.children.append(RequirementNode(
                level=2, level_name="Major System", allocation="SDS",
                chapter_code="SDS-Ch 2: Propulsion & Manoeuvring",
                derived_name=f"Extra {i}",
                technical_requirement=f"The System shall do thing {i}.",
                rationale="R.", system_hierarchy_id="SBS 200 (Propulsion)",
            ))
        errors = validate_tree_structure(tree, ref_data, max_depth=4, max_breadth=3)
        assert any("breadth" in e.message.lower() or "children" in e.message.lower() for e in errors)

    def test_tbd_without_notes(self, ref_data):
        tree = _make_valid_tree()
        tree.root.technical_requirement = "The Vessel shall provide [TBD] MW."
        tree.root.confidence_notes = None
        errors = validate_tree_structure(tree, ref_data, max_depth=4, max_breadth=3)
        assert any("TBD" in e.message or "confidence" in e.message.lower() for e in errors)
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
pytest tests/test_validator.py -v
```

Expected: FAIL

- [ ] **Step 3: Implement validator.py**

```python
# src/validator.py
import json
import logging
import time

import anthropic

from src.config import ANTHROPIC_API_KEY, MODEL
from src.cost_tracker import CostTracker
from src.loader import WorkbookData
from src.models import RequirementNode, RequirementTree, ValidationIssue, ValidationResult, SemanticReview
from src.prompts import format_judge_prompt

logger = logging.getLogger(__name__)


def validate_tree_structure(
    tree: RequirementTree,
    ref_data: WorkbookData,
    max_depth: int,
    max_breadth: int,
) -> list[ValidationIssue]:
    """Run all structural (deterministic) checks on the tree. Returns list of issues."""
    issues: list[ValidationIssue] = []
    if not tree.root:
        return issues

    valid_chapters = set(ref_data.gtr_chapters + ref_data.sds_chapters)
    valid_hierarchy = {h["id"] for h in ref_data.system_hierarchy}
    valid_allocations = {"GTR", "SDS", "GTR / SDS"}

    def _check_node(node: RequirementNode, path: str, parent_level: int | None) -> None:
        # Check "shall"
        if "shall" not in node.technical_requirement.lower():
            issues.append(ValidationIssue(
                severity="error", node_path=path,
                message=f"Technical requirement missing 'shall': \"{node.technical_requirement[:60]}...\""
            ))

        # Check allocation
        if node.allocation not in valid_allocations:
            issues.append(ValidationIssue(
                severity="error", node_path=path,
                message=f"Invalid allocation '{node.allocation}'"
            ))

        # Check chapter code
        if node.chapter_code != "Information Not Found" and node.chapter_code not in valid_chapters:
            issues.append(ValidationIssue(
                severity="warning", node_path=path,
                message=f"Chapter code '{node.chapter_code}' not in reference data"
            ))

        # Check system hierarchy
        if node.system_hierarchy_id != "Information Not Found" and node.system_hierarchy_id not in valid_hierarchy:
            issues.append(ValidationIssue(
                severity="warning", node_path=path,
                message=f"System hierarchy ID '{node.system_hierarchy_id}' not in reference data"
            ))

        # Check V&V array lengths
        lengths = [len(node.verification_method), len(node.verification_event), len(node.test_case_descriptions)]
        non_zero = [l for l in lengths if l > 0]
        if non_zero and len(set(non_zero)) > 1:
            issues.append(ValidationIssue(
                severity="error", node_path=path,
                message=f"V&V array length mismatch: methods={lengths[0]}, events={lengths[1]}, cases={lengths[2]}"
            ))

        # Check child level = parent level + 1
        if parent_level is not None and node.level != parent_level + 1:
            issues.append(ValidationIssue(
                severity="error", node_path=path,
                message=f"Child level {node.level} != parent level {parent_level} + 1"
            ))

        # Check max depth
        if node.level > max_depth:
            issues.append(ValidationIssue(
                severity="error", node_path=path,
                message=f"Node at depth {node.level} exceeds max_depth {max_depth}"
            ))

        # Check max breadth
        if len(node.children) > max_breadth:
            issues.append(ValidationIssue(
                severity="error", node_path=path,
                message=f"Node has {len(node.children)} children, exceeds max_breadth {max_breadth}"
            ))

        # Check TBD + confidence_notes
        if "[TBD]" in node.technical_requirement and not node.confidence_notes:
            issues.append(ValidationIssue(
                severity="warning", node_path=path,
                message="Technical requirement contains [TBD] but confidence_notes is empty"
            ))

        # Recurse into children
        for i, child in enumerate(node.children):
            child_path = f"{path} > L{child.level}.{i + 1}"
            _check_node(child, child_path, node.level)

    _check_node(tree.root, f"L{tree.root.level}", None)
    return issues


def run_semantic_judge(
    tree: RequirementTree,
    cost_tracker: CostTracker,
) -> SemanticReview:
    """Run the LLM semantic judge on the full tree."""
    logger.info("Running semantic judge...")

    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
    tree_json = tree.model_dump_json(indent=2, exclude={"validation", "cost"})

    prompt = format_judge_prompt(
        dig_id=tree.dig_id,
        dig_text=tree.dig_text,
        tree_json=tree_json,
    )

    try:
        resp = client.messages.create(
            model=MODEL,
            max_tokens=4096,
            messages=[{"role": "user", "content": prompt}],
        )
        text = resp.content[0].text
        cost_tracker.record(
            call_type="judge", level=0,
            input_tokens=resp.usage.input_tokens,
            output_tokens=resp.usage.output_tokens,
        )

        if "```json" in text:
            text = text.split("```json")[1].split("```")[0]
        elif "```" in text:
            text = text.split("```")[1].split("```")[0]

        result = json.loads(text.strip())
        issues = [
            ValidationIssue(
                severity=i.get("severity", "warning"),
                message=i.get("message", ""),
                node_path=i.get("node_path", ""),
            )
            for i in result.get("issues", [])
        ]
        review = SemanticReview(status=result.get("status", "flag"), issues=issues)
        logger.info(f"  Semantic judge: {review.status} ({len(issues)} issues)")
        return review

    except Exception as e:
        logger.error(f"  Semantic judge failed: {e}")
        return SemanticReview(
            status="error",
            issues=[ValidationIssue(severity="error", message=str(e), node_path="judge")],
        )
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
pytest tests/test_validator.py -v
```

Expected: All PASS

- [ ] **Step 5: Commit**

```bash
git add src/validator.py tests/test_validator.py
git commit -m "feat: add structural validator and semantic judge"
```

---

### Task 10: XLSX Exporter

**Files:**
- Create: `src/exporter.py`
- Create: `tests/test_exporter.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/test_exporter.py
import pytest
from pathlib import Path

from openpyxl import load_workbook

from src.exporter import tree_to_rows, export_trees_to_xlsx
from src.models import RequirementNode, RequirementTree


def _make_tree():
    child = RequirementNode(
        level=2, level_name="Major System", allocation="SDS",
        chapter_code="SDS-Ch 2", derived_name="Propulsion",
        technical_requirement="The Propulsion System shall provide power.",
        rationale="R.", system_hierarchy_id="SBS 200",
        verification_method=["Analysis"], verification_event=["Design Review"],
        test_case_descriptions=["Review docs."],
        acceptance_criteria="Phase 1 review.",
    )
    root = RequirementNode(
        level=1, level_name="Whole Ship", allocation="GTR",
        chapter_code="GTR-Ch 3", derived_name="Speed",
        technical_requirement="The Vessel shall achieve 17 knots.",
        rationale="R.", system_hierarchy_id="SBS 700",
        verification_method=["Test"], verification_event=["Sea Trials"],
        test_case_descriptions=["Speed trial."],
        acceptance_criteria="Phase 5 sea trial.",
        children=[child],
    )
    return RequirementTree(dig_id="9584", dig_text="Ship speed.", root=root)


class TestTreeToRows:
    def test_flattens_tree(self):
        tree = _make_tree()
        rows = tree_to_rows(tree)
        assert len(rows) == 2  # root + 1 child

    def test_row_has_all_columns(self):
        tree = _make_tree()
        rows = tree_to_rows(tree)
        row = rows[0]
        assert "dig_id" in row
        assert "level" in row
        assert "node_id" in row
        assert "parent_id" in row
        assert "technical_requirement" in row
        assert "verification_method" in row

    def test_parent_child_relationship(self):
        tree = _make_tree()
        rows = tree_to_rows(tree)
        root_row = rows[0]
        child_row = rows[1]
        assert child_row["parent_id"] == root_row["node_id"]

    def test_verification_arrays_joined(self):
        tree = _make_tree()
        rows = tree_to_rows(tree)
        # Verification methods should be comma-joined for xlsx
        assert isinstance(rows[0]["verification_method"], str)


class TestExportXlsx:
    def test_creates_xlsx_file(self, tmp_path):
        tree = _make_tree()
        output_path = tmp_path / "test_output.xlsx"
        export_trees_to_xlsx([tree], output_path)
        assert output_path.exists()

    def test_xlsx_has_correct_rows(self, tmp_path):
        tree = _make_tree()
        output_path = tmp_path / "test_output.xlsx"
        export_trees_to_xlsx([tree], output_path)
        wb = load_workbook(output_path)
        ws = wb.active
        assert ws.max_row == 3  # 1 header + 2 data rows
        wb.close()
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
pytest tests/test_exporter.py -v
```

Expected: FAIL

- [ ] **Step 3: Implement exporter.py**

```python
# src/exporter.py
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
    """Flatten a requirement tree into a list of row dicts."""
    rows = []
    if not tree.root:
        return rows

    counter = [0]

    def _flatten(node: RequirementNode, parent_id: str) -> None:
        counter[0] += 1
        node_id = f"{tree.dig_id}-{counter[0]}"
        rows.append({
            "dig_id": tree.dig_id,
            "dig_text": tree.dig_text,
            "node_id": node_id,
            "parent_id": parent_id,
            "level": node.level,
            "level_name": node.level_name,
            "allocation": node.allocation,
            "chapter_code": node.chapter_code,
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
    """Export multiple requirement trees to a single xlsx file."""
    wb = Workbook()
    ws = wb.active
    ws.title = "Decomposed Requirements"

    # Header row
    ws.append(COLUMNS)

    # Data rows
    for tree in trees:
        for row in tree_to_rows(tree):
            ws.append([row.get(col, "") for col in COLUMNS])

    output_path.parent.mkdir(parents=True, exist_ok=True)
    wb.save(output_path)
    logger.info(f"Exported {sum(t.count_nodes() for t in trees)} requirements to {output_path}")
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
pytest tests/test_exporter.py -v
```

Expected: All PASS

- [ ] **Step 5: Commit**

```bash
git add src/exporter.py tests/test_exporter.py
git commit -m "feat: add xlsx exporter with tree flattening and traceability columns"
```

---

### Task 11: CLI Entry Point

**Files:**
- Create: `src/main.py`

- [ ] **Step 1: Implement main.py**

```python
# src/main.py
import argparse
import json
import logging
import sys
import time
from datetime import datetime
from pathlib import Path

from src.config import (
    DEFAULT_MAX_BREADTH, DEFAULT_MAX_DEPTH, MODEL, OUTPUT_JSON_DIR,
    OUTPUT_LOGS_DIR, OUTPUT_XLSX_DIR, XLSX_PATH,
)
from src.cost_tracker import CostTracker
from src.decomposer import decompose_dig
from src.exporter import export_trees_to_xlsx
from src.loader import load_workbook_data
from src.models import RequirementTree, ValidationResult
from src.validator import run_semantic_judge, validate_tree_structure
from src.verifier import apply_vv_to_tree

logger = logging.getLogger("src")


def setup_logging(verbose: bool) -> None:
    """Configure dual logging: file (always DEBUG) + console (INFO or DEBUG)."""
    OUTPUT_LOGS_DIR.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    log_file = OUTPUT_LOGS_DIR / f"{timestamp}.log"

    file_handler = logging.FileHandler(log_file)
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(logging.Formatter(
        "%(asctime)s %(name)s %(levelname)s %(message)s"
    ))

    console_handler = logging.StreamHandler(sys.stderr)
    console_handler.setLevel(logging.DEBUG if verbose else logging.INFO)
    console_handler.setFormatter(logging.Formatter("%(message)s"))

    root_logger = logging.getLogger("src")
    root_logger.setLevel(logging.DEBUG)
    root_logger.addHandler(file_handler)
    root_logger.addHandler(console_handler)

    logger.info(f"Log file: {log_file}")


def _print_tree(node, indent="  ", prefix=""):
    """Print the requirement tree to console."""
    vv_status = "V&V" if node.acceptance_criteria else "no V&V"
    leaf = " (leaf)" if not node.children else ""
    req_preview = node.technical_requirement[:50] + "..." if len(node.technical_requirement) > 50 else node.technical_requirement
    print(f"{indent}{prefix}L{node.level} {node.level_name}: \"{req_preview}\"  {vv_status}{leaf}")

    for i, child in enumerate(node.children):
        is_last = i == len(node.children) - 1
        child_prefix = "\u2514\u2500 " if is_last else "\u251c\u2500 "
        child_indent = indent + ("   " if is_last else "\u2502  ")
        _print_tree(child, child_indent, child_prefix)


def process_dig(
    dig_id: str,
    dig_text: str,
    ref_data,
    args,
    cost_tracker: CostTracker,
) -> RequirementTree:
    """Process a single DIG through the full pipeline."""
    print(f"\nProcessing DIG {dig_id}: \"{dig_text[:70]}...\"")

    # Phase 1: Decomposition
    tree = decompose_dig(
        dig_id=dig_id,
        dig_text=dig_text,
        ref_data=ref_data,
        max_depth=args.max_depth,
        max_breadth=args.max_breadth,
        skip_vv=args.skip_vv,
        cost_tracker=cost_tracker,
    )

    if not tree.root:
        print("  No requirements generated.")
        return tree

    # Phase 2: V&V
    if not args.skip_vv:
        apply_vv_to_tree(tree, ref_data, cost_tracker)

    # Print tree
    _print_tree(tree.root)

    # Phase 3: Structural validation
    structural_errors = validate_tree_structure(tree, ref_data, args.max_depth, args.max_breadth)
    error_count = sum(1 for e in structural_errors if e.severity == "error")
    warn_count = sum(1 for e in structural_errors if e.severity == "warning")

    if error_count == 0 and warn_count == 0:
        print(f"  Structural validation   \u2713 passed")
    else:
        print(f"  Structural validation   {error_count} error(s), {warn_count} warning(s)")
        for issue in structural_errors:
            print(f"    [{issue.severity}] {issue.node_path}: {issue.message}")

    # Phase 4: Semantic judge
    semantic_review = None
    if not args.skip_judge:
        semantic_review = run_semantic_judge(tree, cost_tracker)
        if semantic_review.status == "pass":
            print(f"  Semantic judge          \u2713 passed")
        else:
            print(f"  Semantic judge          \u26a0 {len(semantic_review.issues)} issue(s)")
            for issue in semantic_review.issues:
                print(f"    [{issue.severity}] {issue.node_path}: {issue.message}")

    tree.validation = ValidationResult(
        structural_errors=structural_errors,
        semantic_review=semantic_review,
    )
    tree.cost = cost_tracker.get_summary()

    # Save JSON
    OUTPUT_JSON_DIR.mkdir(parents=True, exist_ok=True)
    json_path = OUTPUT_JSON_DIR / f"{dig_id}.json"
    json_path.write_text(tree.model_dump_json(indent=2))
    print(f"  Saved: {json_path}")

    # Cost line
    print(f"\n{cost_tracker.format_cost_line()}")
    total_nodes = tree.count_nodes()
    max_d = tree.max_depth()
    print(f"Summary: {total_nodes} requirements generated ({max_d} levels), "
          f"{error_count} errors, {warn_count} warnings")

    return tree


def main():
    parser = argparse.ArgumentParser(description="Decompose shipbuilding DIGs into formal requirements")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--dig", type=str, help="Process a single DIG by DNG ID")
    group.add_argument("--all", action="store_true", help="Process all DIGs")
    group.add_argument("--export-only", action="store_true", help="Export existing JSON to xlsx")

    parser.add_argument("--max-depth", type=int, default=DEFAULT_MAX_DEPTH, help=f"Max decomposition depth (default: {DEFAULT_MAX_DEPTH})")
    parser.add_argument("--max-breadth", type=int, default=DEFAULT_MAX_BREADTH, help=f"Max children per node (default: {DEFAULT_MAX_BREADTH})")
    parser.add_argument("--skip-vv", action="store_true", help="Skip V&V generation")
    parser.add_argument("--skip-judge", action="store_true", help="Skip semantic judge")
    parser.add_argument("--verbose", action="store_true", help="Enable DEBUG logging to console")
    parser.add_argument("--dry-run", action="store_true", help="Estimate API calls without executing")
    parser.add_argument("--force", action="store_true", help="Reprocess DIGs with existing output")
    parser.add_argument("--input", type=str, default=None, help="Path to input xlsx (default: GTR-SDS.xlsx)")

    args = parser.parse_args()
    setup_logging(args.verbose)

    xlsx_path = Path(args.input) if args.input else XLSX_PATH

    # Export-only mode
    if args.export_only:
        json_files = sorted(OUTPUT_JSON_DIR.glob("*.json"))
        if not json_files:
            print("No JSON files found in output/json/")
            return
        trees = []
        for jf in json_files:
            trees.append(RequirementTree.model_validate_json(jf.read_text()))
        OUTPUT_XLSX_DIR.mkdir(parents=True, exist_ok=True)
        output_path = OUTPUT_XLSX_DIR / "results.xlsx"
        export_trees_to_xlsx(trees, output_path)
        print(f"Exported {len(trees)} DIGs to {output_path}")
        return

    # Load workbook
    ref_data = load_workbook_data(xlsx_path)

    # Dry run
    if args.dry_run:
        n = len(ref_data.digs) if args.all else 1
        # Worst case: max_breadth^0 + max_breadth^1 + ... + max_breadth^(max_depth-1) nodes
        max_nodes = sum(args.max_breadth ** i for i in range(args.max_depth))
        calls_per_dig = max_nodes * 2 + 1  # decompose + vv per node + 1 judge
        if args.skip_vv:
            calls_per_dig = max_nodes + 1
        if args.skip_judge:
            calls_per_dig -= 1
        print(f"Dry run: {n} DIGs, max {calls_per_dig} API calls/DIG, max {n * calls_per_dig} total calls")
        return

    # Single DIG mode
    if args.dig:
        if args.dig not in ref_data.digs:
            print(f"Error: DIG {args.dig} not found in workbook")
            sys.exit(1)
        dig = ref_data.digs[args.dig]
        cost_tracker = CostTracker(model=MODEL)
        process_dig(dig["dig_id"], dig["dig_text"], ref_data, args, cost_tracker)
        return

    # Batch mode
    if args.all:
        start_time = time.time()
        batch_tracker = CostTracker(model=MODEL)
        trees = []
        total = len(ref_data.digs)

        for i, (dig_id, dig) in enumerate(ref_data.digs.items(), 1):
            # Skip if output exists (unless --force)
            json_path = OUTPUT_JSON_DIR / f"{dig_id}.json"
            if json_path.exists() and not args.force:
                logger.info(f"[{i}/{total}] Skipping DIG {dig_id} (output exists, use --force to reprocess)")
                trees.append(RequirementTree.model_validate_json(json_path.read_text()))
                continue

            print(f"\n[{i}/{total}]", end="")
            dig_tracker = CostTracker(model=MODEL)
            tree = process_dig(dig["dig_id"], dig["dig_text"], ref_data, args, dig_tracker)
            trees.append(tree)

            # Merge dig costs into batch tracker
            for entry in dig_tracker.get_summary().breakdown:
                batch_tracker.record(entry.call_type, entry.level, entry.input_tokens, entry.output_tokens)

        # Export all to xlsx
        OUTPUT_XLSX_DIR.mkdir(parents=True, exist_ok=True)
        output_path = OUTPUT_XLSX_DIR / "results.xlsx"
        export_trees_to_xlsx(trees, output_path)

        elapsed = time.time() - start_time
        minutes = int(elapsed // 60)
        seconds = int(elapsed % 60)
        summary = batch_tracker.get_summary()
        total_nodes = sum(t.count_nodes() for t in trees)

        print(f"\n{'=' * 40}")
        print(f"Batch Complete")
        print(f"{'=' * 40}")
        print(f"DIGs processed: {total}")
        print(f"Total requirements: {total_nodes}")
        print(f"Total API calls: {summary.api_calls}")
        print(f"Total tokens: {summary.total_input_tokens:,} input / {summary.total_output_tokens:,} output")
        print(f"Total cost: ${summary.total_cost_usd:.2f}")
        print(f"Time elapsed: {minutes}m {seconds}s")
        print(f"Results: {OUTPUT_JSON_DIR} ({total} files)")


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Test manually with dry run**

```bash
python -m src.main --dig 9584 --dry-run
```

Expected: `Dry run: 1 DIGs, max X API calls/DIG, max X total calls`

```bash
python -m src.main --all --dry-run
```

Expected: `Dry run: 108 DIGs, max X API calls/DIG, max X total calls`

- [ ] **Step 3: Commit**

```bash
git add src/main.py
git commit -m "feat: add CLI entry point with single/batch/export modes and logging"
```

---

### Task 12: Strip XLSX Script

**Files:**
- Create: `scripts/strip_xlsx.py`

- [ ] **Step 1: Implement strip script**

```python
# scripts/strip_xlsx.py
"""Strip LLM-generated columns from GTR-SDS.xlsx, keeping only source data."""
import sys
from pathlib import Path

from openpyxl import load_workbook

# Columns to keep in Requirements Decomposition (1-indexed)
KEEP_COLUMNS = {1, 2}  # A=DNG, B=DIG Text

# All other columns (C through L) are stripped
STRIP_COLUMNS = {3, 4, 5, 6, 7, 8, 9, 10, 11, 12}

def main():
    project_root = Path(__file__).parent.parent
    input_path = project_root / "GTR-SDS.xlsx"
    output_dir = project_root / "test"
    output_dir.mkdir(exist_ok=True)
    output_path = output_dir / "GTR-SDS-clean.xlsx"

    print(f"Loading: {input_path}")
    wb = load_workbook(input_path)

    ws = wb["Requirements Decomposition"]

    # Delete columns from right to left to preserve indices
    for col_idx in sorted(STRIP_COLUMNS, reverse=True):
        ws.delete_cols(col_idx)

    print(f"Stripped {len(STRIP_COLUMNS)} columns from Requirements Decomposition tab")
    print(f"Kept: DNG, DIG Text")
    print(f"Reference tabs preserved: {[s.title for s in wb.worksheets if s.title != 'Requirements Decomposition']}")

    wb.save(output_path)
    print(f"Saved: {output_path}")


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Test the script**

```bash
python scripts/strip_xlsx.py
```

Expected: Creates `test/GTR-SDS-clean.xlsx` with only DNG and DIG Text columns in the main tab.

- [ ] **Step 3: Commit**

```bash
git add scripts/strip_xlsx.py
git commit -m "feat: add script to strip LLM-generated columns from xlsx for testing"
```

---

### Task 13: Prompt Tests + End-to-End Smoke Test

**Files:**
- Create: `tests/test_prompts.py`

- [ ] **Step 1: Write prompt loading tests**

```python
# tests/test_prompts.py
import pytest
from src.prompts import format_decompose_prompt, format_vv_prompt, format_judge_prompt


class TestFormatDecomposePrompt:
    def test_loads_and_formats(self):
        result = format_decompose_prompt(
            dig_id="9584",
            dig_text="The ship must do 17 knots.",
            target_level=2,
            target_level_name="Major System",
            parent_scope="Whole Ship",
            child_scope="Major System",
            parent_chain="Level 1: The Vessel shall...",
            system_hierarchy="SBS 200 (Propulsion)",
            chapter_list="SDS-Ch 2",
            max_breadth=3,
        )
        assert "9584" in result
        assert "Major System" in result
        assert "17 knots" in result
        assert "shall" in result.lower()

    def test_includes_levels_example(self):
        result = format_decompose_prompt(
            dig_id="1", dig_text="text", target_level=1,
            target_level_name="Whole Ship", parent_scope="DIG",
            child_scope="Whole Ship", parent_chain="",
            system_hierarchy="", chapter_list="", max_breadth=3,
        )
        assert "Decomposition Levels Example" in result


class TestFormatVvPrompt:
    def test_loads_and_formats(self):
        result = format_vv_prompt(
            level=1, level_name="Whole Ship",
            technical_requirement="The Vessel shall achieve 17 knots.",
            system_hierarchy_id="SBS 700",
            acceptance_phases="Phase 1", verification_methods="Test",
            verification_events="Sea Trials",
        )
        assert "17 knots" in result
        assert "Phase 1" in result


class TestFormatJudgePrompt:
    def test_loads_and_formats(self):
        result = format_judge_prompt(
            dig_id="9584", dig_text="Ship speed.",
            tree_json='{"root": {}}',
        )
        assert "9584" in result
        assert "independent requirements reviewer" in result.lower()
```

- [ ] **Step 2: Run tests**

```bash
pytest tests/test_prompts.py -v
```

Expected: All PASS

- [ ] **Step 3: End-to-end smoke test (requires valid API key)**

Ensure `.env` has a valid `ANTHROPIC_API_KEY`, then:

```bash
# Cheapest test: single DIG, depth 1, no judge
python -m src.main --dig 9584 --max-depth 1 --max-breadth 1 --skip-judge --verbose

# Depth 2 with judge
rm -f output/json/9584.json
python -m src.main --dig 9584 --max-depth 2 --max-breadth 2 --verbose

# Export to xlsx
python -m src.main --export-only

# Full depth
rm -f output/json/9584.json
python -m src.main --dig 9584 --verbose
```

Check `output/json/9584.json` has: root with children, validation, and cost fields populated.

- [ ] **Step 4: Commit**

```bash
git add tests/test_prompts.py
git commit -m "test: add prompt loading tests and smoke test instructions"
```

---

### Task 14: Initial Git Push

- [ ] **Step 1: Review all files**

```bash
git status
git log --oneline
```

- [ ] **Step 2: Push to remote**

```bash
git push -u origin main
```

Expected: Code pushed to https://github.com/jude-sph/Requirements.git
