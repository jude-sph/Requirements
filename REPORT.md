# Requirements Decomposition Tool — User Report

## What This Tool Does

This tool takes a Design Instruction or Guideline (DIG) from the Polar Icebreaker GTR/SDS workbook and automatically breaks it down into a hierarchy of formal "shall" requirements across four levels:

| Level | Name         | Example                                                         |
|-------|--------------|-----------------------------------------------------------------|
| 1     | Whole Ship   | "The Vessel shall achieve a forward speed of at least 17 knots" |
| 2     | Major System | "The Propulsion System shall provide [X] MW of delivered power" |
| 3     | Subsystem    | "Each Podded Propulsor shall be rated for [Y] kW at [Z] RPM"   |
| 4     | Equipment    | "The Propulsion Motor shall maintain winding temp below 120 C"  |

Each requirement is allocated to the correct GTR or SDS chapter, mapped to the System Breakdown Structure (SBS), and given verification & validation data (methods, events, acceptance criteria, and test cases).

The output follows IEEE 29481 "shall" statement conventions and ISO 15288 decomposition principles.

---

## How to Use It

### Setup (One-Time)

1. Install Python 3.10 or later
2. Open a terminal in the project folder and run:
   ```
   pip install -r requirements.txt
   ```
3. Open the `.env` file and paste your Anthropic API key:
   ```
   ANTHROPIC_API_KEY=sk-ant-your-key-here
   MODEL=claude-sonnet-4-6
   ```

### Running a Single DIG

To decompose one DIG (e.g., DIG 9584):

```
python -m src.main --dig 9584
```

You will see a tree printed to the console showing the generated requirements at each level, followed by validation results and cost.

### Running All DIGs

To process the full workbook (109 DIGs):

```
python -m src.main --all
```

Each DIG is saved independently, so if the run is interrupted you can restart it and already-processed DIGs will be skipped. Use `--force` to reprocess everything from scratch.

### Exporting to Excel

After processing, combine all results into a single spreadsheet:

```
python -m src.main --export-only
```

This creates `output/xlsx/results.xlsx` with one row per requirement. The `node_id` and `parent_id` columns preserve the parent-child traceability.

### Quick Iteration

For faster turnaround while tuning or reviewing, you can limit the depth and breadth:

```
python -m src.main --dig 9584 --max-depth 2 --max-breadth 1 --skip-vv
```

This generates fewer requirements and skips V&V, which is useful for checking decomposition quality before committing to a full run.

### Estimating Cost Before Running

```
python -m src.main --all --dry-run
```

This estimates how many API calls and tokens will be used without actually calling the AI.

---

## How the System Works

The tool processes each DIG through five phases, each designed to do one job well.

### Phase 1 — Decomposition

The AI receives the DIG text and generates Level 1 requirements. For each Level 1 requirement, it then generates Level 2 children, and so on down to Level 4. At every step, the AI sees the full chain of parent requirements above it so that deeper requirements stay consistent with the ones above.

The AI is given the SBS hierarchy, GTR/SDS chapter lists, and a worked example (the 17-knot speed requirement) so it knows what good decomposition looks like.

If further breakdown would be artificial (e.g., a policy statement with no equipment-level implication), the AI stops that branch early rather than forcing meaningless subdivisions.

### Phase 2 — Verification & Validation

For each requirement in the tree, the AI generates:
- **Acceptance criteria** across the five project phases (Design Verification through Final Vessel Acceptance)
- **Verification methods** (Test, Analysis, Inspection, Demonstration, Review, or Third Party Certification)
- **Verification events** (Design Disclosure, FAT, HAT, SAT, Sea Trials, or Certification)
- **Test case descriptions** explaining how each method/event pair would be carried out

### Phase 3 — Structural Checks

A set of automated (non-AI) checks confirms that:
- Every requirement contains a "shall" statement
- Allocations are valid (GTR, SDS, or GTR / SDS)
- Chapter codes and SBS IDs exist in the reference data
- V&V arrays are properly formed
- Parent-child levels are sequential
- Any [TBD] placeholders have an explanation

### Phase 4 — Independent Review

The AI is called again in a separate "judge" role. Acting as an independent auditor, it reviews the entire tree for issues such as:
- A child requirement that doesn't logically follow from its parent
- Incorrect chapter or SBS allocation
- Requirements that are too vague or too specific for their level
- Verification approaches that don't suit the requirement

### Phase 5 — Correction

If the judge flags issues, the AI corrects the tree based on the feedback, then the structural checks and judge review run again to confirm the fixes are sound. This happens once (not in an endless loop) to balance quality against cost.

---

## What Goes In, What Comes Out

### Input

The source file is `GTR-SDS.xlsx`. The tool reads:
- The **Requirements Decomposition** sheet (DIG IDs and text)
- Reference sheets for system hierarchy, GTR/SDS chapters, acceptance phases, verification methods, and verification events

You do not need to modify the workbook. If you have a different input file, use `--input /path/to/file.xlsx`.

### Output

| Location | Contents |
|----------|----------|
| `output/json/[DIG_ID].json` | Full requirement tree with traceability, V&V data, validation results, and cost breakdown |
| `output/xlsx/results.xlsx` | Flattened spreadsheet (one row per requirement) for review in Excel |
| `output/logs/[timestamp].log` | Detailed log of every AI call, useful for auditing or troubleshooting |

---

## Cost

The tool tracks token usage and cost for every AI call. A typical DIG costs roughly $0.05-$0.10 USD using the default model (Claude Sonnet). The full 109-DIG workbook might cost around $5-$10 depending on complexity.

Three models are available:

| Model | Relative Cost | Best For |
|-------|--------------|----------|
| Claude Haiku | Lowest | Quick iteration, testing |
| Claude Sonnet (default) | Medium | Production runs |
| Claude Opus | Highest | Maximum quality on difficult DIGs |

Change the model in `.env` by setting `MODEL=claude-haiku-4-5` or `MODEL=claude-opus-4-6`.

---

## Key Design Decisions

**Why separate AI calls instead of one big prompt?**
Earlier attempts that asked the AI to decompose, allocate, and verify all at once produced only shallow (Level 1) results. Splitting responsibilities into focused prompts — one for decomposition, one for V&V, one for review — produces deeper, more consistent output.

**Why a judge-then-refine step?**
Requirements engineering demands internal consistency. The independent judge catches errors that the decomposition step might introduce (wrong chapter codes, illogical parent-child relationships). The correction step fixes them without starting over.

**Why depth-first traversal?**
By fully expanding one branch before moving to the next, each requirement always has its complete ancestry available. This keeps Level 4 equipment requirements traceable all the way back to the original DIG.
