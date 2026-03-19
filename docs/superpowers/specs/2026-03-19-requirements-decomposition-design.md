# Requirements Decomposition System — Design Spec

## Overview

A Python CLI tool that uses the Claude API to decompose high-level shipbuilding Design Instructions and Guidelines (DIGs) into multi-level formal requirements compliant with IEEE 29481 ("shall" statements) and ISO 15288 (system breakdown structure).

The system addresses a known failure mode of previous attempts: single-level decomposition caused by overloaded prompts. This design uses focused, single-responsibility LLM calls in a sequential pipeline to achieve 4-level decomposition depth.

**Domain:** Canadian Coast Guard Polar Icebreaker (PIB) requirements engineering.

## Problem Statement

High-level DIGs (e.g., "The ship must be capable of 17 knots") need to be decomposed into formal technical requirements at multiple levels of the system hierarchy:

| Level | Scope | Example |
|-------|-------|---------|
| 1 | Whole Ship | "The Vessel shall achieve a maximum attainable forward speed of at least 17 knots..." |
| 2 | Major System | "The Propulsion System shall provide a minimum delivered power of [X] MW..." |
| 3 | Subsystem | "Each Azimuthing Podded Propulsor shall be rated for [Y] kW at [Z] RPM..." |
| 4 | Equipment | "The Propulsion Motor shall maintain a winding temperature not exceeding 120°C..." |

Each level also requires: allocation (GTR/SDS/both), chapter code, rationale, system hierarchy ID, acceptance criteria, verification method(s), verification event(s), and test case description(s).

Previous AI attempts only produced Level 1 outputs because the prompts tried to handle decomposition, allocation, and V&V all at once.

## Architecture: Two-Phase Pipeline per Level

### Core Principle

Each DIG is processed through a sequential pipeline. At each level, two focused LLM calls are made:

1. **Decomposition call** — derives the technical requirement, allocation, chapter, rationale, system hierarchy ID
2. **V&V call** — generates acceptance criteria, verification methods/events, test case descriptions

This runs top-down: Level 1 → Level 2 → Level 3 → Level 4. Each level receives the full chain of parent outputs as context.

### Pipeline Flow

The pipeline is a **depth-first tree traversal**. At each node, the LLM may produce 1–N child requirements (bounded by `--max-breadth`), and each child is then recursively decomposed (bounded by `--max-depth`).

```
DIG Text
  │
  ▼
[Decompose Level 1] → [V&V Level 1]
  ├── child 1 → [Decompose Level 2] → [V&V Level 2]
  │     ├── child 1a → [Decompose Level 3] → [V&V Level 3]
  │     │     └── child 1a-i → [Decompose Level 4] → [V&V Level 4]
  │     └── child 1b → [Decompose Level 3] → [V&V Level 3]
  └── child 2 → [Decompose Level 2] → [V&V Level 2]
        └── ...
  │
  ▼
[Structural Validation]  (Python — deterministic checks, full tree)
  │
  ▼
[Semantic Judge]  (LLM — coherence and quality review, full tree)
  │
  ▼
[Save JSON + Export XLSX]
```

**Fan-out:** At each level, the decomposition call may identify multiple child requirements (e.g., a speed DIG at Level 1 may produce both a propulsion power requirement and a hull resistance requirement at Level 2). The number of children per node is bounded by `--max-breadth` (default: 3).

**Depth control:** The tree depth is bounded by `--max-depth` (default: 4, matching the 4 hierarchy levels: Whole Ship → Major System → Subsystem → Equipment).

**Early termination:** If the LLM determines further decomposition would be artificial (e.g., a policy requirement with no equipment mapping), it returns a `decomposition_complete: true` signal and that branch stops. This can happen at any level.

**Accumulated context:** Each decomposition call receives the DIG text plus the full ancestor chain (root → parent). This ensures deep nodes see the complete derivation path for coherent requirements.

## Data Model

Internal representation is a **recursive tree**. Each DIG produces one tree where each node may have multiple children (bounded by `--max-breadth`):

```json
{
  "dig_id": "9584",
  "dig_text": "The ship must be capable of...",
  "root": {
    "level": 1,
    "level_name": "Whole Ship",
    "allocation": "GTR",
    "chapter_code": "GTR-Ch 3",
    "derived_name": "Maximum Forward Speed",
    "technical_requirement": "The Vessel shall achieve...",
    "rationale": "Direct transposition of DIG 9584...",
    "system_hierarchy_id": "SBS 700 (Trials)",
    "acceptance_criteria": "Progressive verification across phases...",
    "verification_method": ["Analysis", "Test"],
    "verification_event": ["Design Review", "Sea Trials"],
    "test_case_descriptions": [
      "Review propulsion analysis...",
      "Conduct sea trial speed runs..."
    ],
    "confidence_notes": null,
    "decomposition_complete": false,
    "children": [
      {
        "level": 2,
        "level_name": "Major System",
        "allocation": "SDS",
        "chapter_code": "SDS-Ch 2",
        "derived_name": "Propulsion Power Delivery",
        "technical_requirement": "The Propulsion System shall provide...",
        "rationale": "...",
        "system_hierarchy_id": "SBS 200 (Propulsion)",
        "acceptance_criteria": "...",
        "verification_method": ["Analysis", "Demonstration"],
        "verification_event": ["Design Review", "HAT"],
        "test_case_descriptions": ["...", "..."],
        "confidence_notes": "Power value [TBD] - requires propulsion study",
        "decomposition_complete": false,
        "children": [
          {
            "level": 3,
            "level_name": "Subsystem",
            "children": []
          }
        ]
      },
      {
        "level": 2,
        "level_name": "Major System",
        "allocation": "SDS",
        "chapter_code": "SDS-Ch 1",
        "derived_name": "Hull Resistance Envelope",
        "technical_requirement": "The Hull Form shall...",
        "children": []
      }
    ]
  },
  "validation": {
    "structural_errors": [],
    "semantic_review": {
      "status": "pass",
      "issues": []
    }
  }
}
```

Key constraints:
- Each node has a `children` array (empty if leaf node or `decomposition_complete: true`)
- `verification_method`, `verification_event`, and `test_case_descriptions` are arrays of matching length
- `confidence_notes` is populated when values are estimated or use placeholders ([TBD]); if `technical_requirement` contains `[TBD]`, `confidence_notes` must be non-null
- Known values from the DIG are preserved exactly; unknowns get placeholders with explanatory notes
- Pydantic models enforce schema compliance on LLM output
- The xlsx export flattens the tree into rows with `level`, `parent_id`, and `node_id` columns for traceability

## Source Data Mapping

The xlsx column `DNG` maps to `dig_id` in the data model. The `--dig` CLI flag accepts a DNG number.

**Sheet-to-field mapping for reference data:**

| xlsx Sheet Name | Contains | Maps to Data Model Field |
|----------------|----------|--------------------------|
| "Verification Events" | Methods (Test, Inspection, Demonstration, Analysis, Review) | `verification_method` |
| "Verification Means" | Events (Design Disclosure, FAT, HAT, SAT, CST, Third Party Cert) | `verification_event` |
| "Acceptance Phases" | 5 phases (Design Verification → Final Vessel Acceptance) | `acceptance_criteria` reference |
| "System Hierarchy" | SBS tree (100-900 blocks with sub-systems) | `system_hierarchy_id` reference |
| "GTR Chapters" | 11 chapters with sub-sections | `chapter_code` reference (GTR allocation) |
| "SDS Chapters" | 20 chapters in 8 parts | `chapter_code` reference (SDS allocation) |

**Note:** The xlsx sheet names are misleading — "Verification Events" contains what we call methods, and "Verification Means" contains what we call events. `loader.py` must map these correctly.

**Data cleaning:** `loader.py` must strip leading/trailing whitespace from all cell values. The source data contains inconsistent whitespace (e.g., `" GTR / SDS"` vs `"GTR / SDS"`).

**Duplicate handling:** DIG 10237 appears twice in the source data. `loader.py` should warn on duplicates and use the first occurrence.

## Project Structure

```
Requirements/
├── GTR-SDS.xlsx                    # Source data (existing)
├── levels-example.png              # Reference image (existing)
├── src/
│   ├── __init__.py
│   ├── main.py                     # CLI entry point
│   ├── config.py                   # API key, model settings, file paths
│   ├── loader.py                   # Read xlsx: DIGs, system hierarchy, chapters, V&V refs
│   ├── decomposer.py              # Level-by-level decomposition (LLM calls)
│   ├── verifier.py                # V&V generation per level (LLM calls)
│   ├── prompts.py                 # Prompt template loading and formatting
│   ├── validator.py               # Structural checks (Python) + semantic judge (LLM)
│   ├── exporter.py                # JSON tree → xlsx export
│   ├── cost_tracker.py            # Token usage and cost tracking per API call
│   └── models.py                  # Pydantic models for data structures
├── output/
│   ├── json/                       # Per-DIG JSON trees
│   ├── xlsx/                       # Exported spreadsheets
│   └── logs/                       # Per-run log files (DEBUG level)
├── prompts/
│   ├── decompose_level.txt         # Decomposition prompt template
│   ├── generate_vv.txt             # V&V generation prompt template
│   ├── semantic_judge.txt          # Semantic review prompt template
│   └── levels_example.txt          # Worked example (from levels-example.png)
├── scripts/
│   └── strip_xlsx.py               # Strip LLM-generated columns from GTR-SDS.xlsx for testing
├── .env                            # ANTHROPIC_API_KEY, MODEL
└── requirements.txt                # anthropic, openpyxl, pydantic, python-dotenv
```

## Test Data Preparation

`scripts/strip_xlsx.py` produces a clean input file from `GTR-SDS.xlsx` by removing all LLM-generated columns, leaving only source data.

**Kept:**
- `DNG` column (source ID)
- `DIG Text` column (source requirement)
- All reference tabs: System Hierarchy, GTR Chapters, SDS Chapters, Acceptance Phases, Verification Events, Verification Means

**Stripped from Requirements Decomposition tab:**
- Allocation, Chapter Code, Derived Name, Technical Requirement, Rationale, System Hierarchy ID, Acceptance Criteria, Verification Method, Verification Event, Test Case Description

**Usage:**
```bash
python scripts/strip_xlsx.py            # Outputs test/GTR-SDS-clean.xlsx
```

This allows running the decomposition tool on the clean file and comparing output against the original for manual review.

## CLI Interface

```bash
# Process a single DIG by ID (defaults: --max-depth 4, --max-breadth 3)
python -m src.main --dig 9584

# Process all DIGs
python -m src.main --all

# Restrict decomposition: 2 levels deep, 1 child per node (fast/cheap iteration)
python -m src.main --dig 9584 --max-depth 2 --max-breadth 1

# Full fan-out: 4 levels, up to 5 children per node
python -m src.main --dig 9584 --max-depth 4 --max-breadth 5

# Process a single DIG, skip V&V (faster iteration on decomposition quality)
python -m src.main --dig 9584 --skip-vv

# Process a single DIG, skip semantic judge
python -m src.main --dig 9584 --skip-judge

# Export existing JSON results to xlsx (no API calls)
python -m src.main --export-only

# Dry run: count DIGs and estimate API calls without executing
python -m src.main --all --dry-run
```

Console output (tree display reflecting fan-out):
```
Processing DIG 9584: "The ship must be capable of..."
  L1 Whole Ship: "The Vessel shall achieve..."           ✓ decomposed  ✓ V&V
  ├─ L2 Major System: "The Propulsion System shall..."   ✓ decomposed  ✓ V&V
  │  ├─ L3 Subsystem: "Each Podded Propulsor shall..."   ✓ decomposed  ✓ V&V
  │  │  └─ L4 Equipment: "The Propulsion Motor shall..." ✓ decomposed  ✓ V&V
  │  └─ L3 Subsystem: "The Shaftline shall..."           ✓ decomposed  ✓ V&V (leaf)
  └─ L2 Major System: "The Hull Form shall..."           ✓ decomposed  ✓ V&V (leaf)
  Structural validation   ✓ passed
  Semantic judge          ⚠ 1 warning: Level 2 chapter allocation may be incorrect
  Saved: output/json/9584.json

Cost: 13 API calls | 42,350 input tokens | 8,120 output tokens | $0.0847
Summary: 6 requirements generated (4 levels), 0 errors, 1 warning
```

For batch runs (`--all`), a running total is shown plus a final summary:
```
... (per-DIG output) ...

═══ Batch Complete ═══
DIGs processed: 109/109
Total requirements: 847
Total API calls: 1,247
Total tokens: 4,821,300 input / 923,400 output
Total cost: $9.42
Time elapsed: 47m 12s
Results: output/json/ (109 files)
```

Default model: `claude-sonnet-4-6` (latest Sonnet, cost-efficient for high call volume; configurable via .env).

## Cost Tracking

`cost_tracker.py` provides accurate per-call and per-run cost tracking using token counts from the Anthropic API response `usage` field.

**Per API call, track:**
- Input tokens, output tokens (from `response.usage`)
- Call type (decompose, vv, judge)
- Associated DIG ID and level
- Calculated cost based on model pricing

**Pricing table** (stored in `config.py`, easily updated):
```python
MODEL_PRICING = {
    "claude-sonnet-4-6": {"input_per_mtok": 3.00, "output_per_mtok": 15.00},
    "claude-opus-4-6": {"input_per_mtok": 15.00, "output_per_mtok": 75.00},
    "claude-haiku-4-5": {"input_per_mtok": 0.80, "output_per_mtok": 4.00},
}
```

**Cost data is saved** in the JSON output alongside the requirement tree:
```json
{
  "dig_id": "9584",
  "root": { "..." },
  "validation": { "..." },
  "cost": {
    "total_input_tokens": 42350,
    "total_output_tokens": 8120,
    "total_cost_usd": 0.0847,
    "api_calls": 13,
    "breakdown": [
      {"call_type": "decompose", "level": 1, "input_tokens": 3200, "output_tokens": 620, "cost_usd": 0.0189},
      {"call_type": "vv", "level": 1, "input_tokens": 2800, "output_tokens": 540, "cost_usd": 0.0165}
    ]
  }
}
```

## Logging

Extensive logging using Python's `logging` module with two outputs:

**Console (stderr):** INFO level by default. Shows progress, warnings, errors. Use `--verbose` for DEBUG level.

**Log file:** DEBUG level always. Written to `output/logs/{run_timestamp}.log`. Captures:
- Every API call: model, prompt length, response length, tokens used, cost, latency
- Full prompts sent and responses received (at DEBUG level)
- Structural validation results per node
- Semantic judge input and output
- Retry attempts and failures
- Per-DIG and per-run cost summaries

```bash
# Normal run (INFO to console)
python -m src.main --dig 9584

# Verbose run (DEBUG to console + log file)
python -m src.main --dig 9584 --verbose
```

## Prompt Strategy

### Decomposition Prompt

- **Role**: Naval systems engineer performing requirements decomposition per ISO 15288
- **Context**: System hierarchy tree, chapter list (GTR or SDS), worked example from `levels_example.txt`
- **Input**: DIG text + all parent-level outputs generated so far
- **Task**: "Derive the Level N child requirements from this parent. You are decomposing from [parent scope] to [child scope]. Return 1 to N children (N bounded by max-breadth)."
- **Output**: Strict JSON matching Pydantic schema
- **Constraints**:
  - Do not add features not mentioned in the DIG
  - Use [TBD] with explanatory note when values cannot be derived from source
  - If further decomposition is not meaningful, return `decomposition_complete: true`
  - Must use IEEE 29481 "shall" format

### V&V Prompt

- **Role**: Verification and validation engineer
- **Context**: 5 acceptance phases, verification methods/events reference tables
- **Input**: Technical requirement from decomposition step
- **Task**: Generate V&V data maximising early verification coverage across all 5 phases
- **Constraint**: Independent test case description for each verification method/event pair

### Semantic Judge Prompt

- **Role**: Independent requirements reviewer (adversarial — find problems)
- **Input**: Complete requirement tree for one DIG
- **Checklist**: Parent-child coherence, allocation correctness, specificity progression, V&V appropriateness, placeholder justification
- **Output**: List of issues with severity (error/warning) or explicit "PASS"

### Why This Should Work

1. Single responsibility per call — decompose OR verify, never both
2. Explicit level targeting — "you are generating Level 3" not "decompose to all levels"
3. Accumulated context — each level sees all prior outputs
4. Worked example — concrete decomposition pattern embedded in every prompt
5. Structured output — Pydantic schema enforcement prevents drift into prose

## Validation

### Structural Checks (Python — deterministic)

- Technical requirement contains "shall"
- Chapter code exists in GTR/SDS chapter reference data
- System hierarchy ID exists in system hierarchy reference data
- Allocation is valid: "GTR", "SDS", or "GTR / SDS"
- Verification method/event/test-case arrays are same length
- All required fields are populated
- Child level = parent level + 1
- No node exceeds `--max-depth`
- No node has more children than `--max-breadth`
- If `technical_requirement` contains `[TBD]`, then `confidence_notes` must be non-null

### Semantic Judge (LLM — reasoning)

- Does each child requirement genuinely refine its parent?
- Is the system hierarchy allocation appropriate for the level?
- Are [TBD] placeholders justified (not lazy)?
- Is the specificity appropriate per level (not too abstract, not too detailed)?
- Do verification methods make sense for the requirement type?

## Reference Data (loaded from xlsx)

The following reference data is extracted from GTR-SDS.xlsx at startup and injected into prompts:

- **System Hierarchy**: 7 top-level blocks (100 Hull, 200 Propulsion, 300 Electrical, 400 C4I, 500 Auxiliary, 600 Outfitting, 900 ILS) with 2-4 levels of sub-systems
- **GTR Chapters**: 11 chapters with sub-sections (whole-vessel concerns)
- **SDS Chapters**: 20 chapters in 8 parts (system-specific concerns)
- **Acceptance Phases**: Phase 1 (Design Verification) through Phase 5 (Final Vessel Acceptance)
- **Verification Methods**: Test, Inspection, Demonstration, Analysis, Review, 3rd Party Cert
- **Verification Events**: Design Review, FAT, HAT, SAT, Sea/Ice Trials, Certification

## Worked Example (levels_example.txt)

Stored at `prompts/levels_example.txt`, transcribed from levels-example.png:

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

## Dependencies

```
anthropic>=0.40.0
openpyxl>=3.1.0
pydantic>=2.0.0
python-dotenv>=1.0.0
```

## Error Handling

- **Transient API failures** (rate limits, timeouts, 500s): `decomposer.py` and `verifier.py` implement retry with exponential backoff (3 attempts, 1s/2s/4s delays). After 3 failures, the node is marked with an error and processing continues to the next sibling/branch.
- **Malformed LLM output** (fails Pydantic validation): Logged as a structural error on that node. No retry — the prompt needs tuning, not re-rolling.
- **Batch resilience** (`--all`): Since each DIG saves to its own JSON file, a crash mid-batch loses only the in-progress DIG. Re-running `--all` skips DIGs with existing output files (use `--force` to reprocess).

## Out of Scope

- Web UI (can be added later)
- Provider abstraction (Claude only for now)
- Automated retry on structural validation failure (manual iteration first)
