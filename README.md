# reqdecomp — Requirements Decomposition System

Decomposes high-level shipbuilding Design Instructions and Guidelines (DIGs) into multi-level formal "shall" requirements using LLMs.

Each DIG is decomposed through up to 4 levels of the system hierarchy:

```
Level 1: Whole Ship  →  Level 2: Major System  →  Level 3: Subsystem  →  Level 4: Equipment
```

At each level, the system generates:
- IEEE 29481 compliant "shall" statement
- GTR/SDS chapter allocation
- System hierarchy mapping
- Rationale and traceability
- Verification & Validation data (5-phase progressive acceptance)

A semantic judge reviews each decomposition tree and a refinement step automatically corrects flagged issues.

## Install

```bash
git clone https://github.com/jude-sph/Requirements.git
cd Requirements
pip install -e .
```

## Setup

Run the interactive setup to configure your model and API keys:

```bash
reqdecomp --setup
```

This lets you pick from several models:

| Model | Provider | Est. Cost/DIG |
|-------|----------|---------------|
| Claude Sonnet 4.6 | Anthropic | ~$0.20-0.40 |
| Claude Haiku 4.5 | Anthropic | ~$0.05-0.10 |
| Gemini 2.5 Flash | OpenRouter | ~$0.01-0.03 |
| DeepSeek V3 | OpenRouter | ~$0.02-0.05 |
| GPT-4o Mini | OpenRouter | ~$0.01-0.03 |

Or manually create a `.env` file:

```
PROVIDER=anthropic
ANTHROPIC_API_KEY=sk-ant-...
MODEL=claude-sonnet-4-6
```

For OpenRouter models:

```
PROVIDER=openrouter
OPENROUTER_API_KEY=sk-or-...
MODEL=google/gemini-2.5-flash
```

## Usage

```bash
# Process a single DIG
reqdecomp --dig 9584

# Process with restricted depth (cheaper)
reqdecomp --dig 9584 --max-depth 2 --max-breadth 1

# Skip the semantic judge (faster)
reqdecomp --dig 9584 --skip-judge

# Estimate cost before running
reqdecomp --dry-run --all

# Process all DIGs
reqdecomp --all

# Export results to xlsx
reqdecomp --export-only
```

### Options

| Flag | Description |
|------|-------------|
| `--dig ID` | Process a single DIG by its DNG number |
| `--all` | Process all DIGs in the workbook |
| `--export-only` | Export existing JSON results to xlsx |
| `--setup` | Configure model and API keys |
| `--max-depth N` | Max decomposition depth, 1-4 (default: 4) |
| `--max-breadth N` | Max children per node (default: 3) |
| `--skip-vv` | Skip V&V generation (faster, cheaper) |
| `--skip-judge` | Skip semantic judge and refinement |
| `--verbose` | Show detailed debug output |
| `--dry-run` | Estimate API calls without running |
| `--force` | Reprocess DIGs that already have output |
| `--input PATH` | Use a different input xlsx |

## Output

| Location | Contents |
|----------|----------|
| `output/json/` | Per-DIG JSON trees (source of truth) |
| `output/xlsx/results.xlsx` | Flattened spreadsheet export |
| `output/logs/` | Detailed per-run log files |

## How It Works

For each DIG, the system runs a two-phase pipeline at each level:

1. **Decompose** — LLM derives child requirements from the parent
2. **V&V** — LLM generates verification and validation data

After the full tree is built:

3. **Structural validation** — Python checks for "shall" format, valid chapter codes, array consistency
4. **Semantic judge** — LLM reviews the tree for coherence, specificity, and correctness
5. **Refinement** — If issues are found, the tree is refined based on judge feedback
6. **Final judge** — Re-reviews the refined tree; remaining issues are saved as guidance

## Project Structure

```
src/
├── main.py          CLI entry point
├── config.py        Settings and pricing
├── llm_client.py    Unified LLM client (Anthropic + OpenRouter)
├── loader.py        XLSX data loading
├── decomposer.py    Requirement decomposition
├── verifier.py      V&V generation
├── validator.py     Structural checks + semantic judge
├── refiner.py       Judge-feedback refinement
├── exporter.py      JSON to XLSX export
├── cost_tracker.py  Token/cost tracking
├── prompts.py       Prompt template loading
└── models.py        Pydantic data models

prompts/             Prompt templates (editable)
scripts/
├── configure.py     Interactive setup wizard
└── strip_xlsx.py    Strip LLM columns from source xlsx
```

## Development

```bash
pip install -e ".[dev]"
pytest -v
```
