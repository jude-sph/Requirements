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
from src.refiner import refine_tree
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

    # Phase 4: Semantic judge + refinement loop
    semantic_review = None
    if not args.skip_judge:
        semantic_review = run_semantic_judge(tree, cost_tracker)
        if semantic_review.status == "pass":
            print(f"  Semantic judge          \u2713 passed")
        else:
            print(f"  Semantic judge          \u26a0 {len(semantic_review.issues)} issue(s)")
            for issue in semantic_review.issues:
                print(f"    [{issue.severity}] {issue.node_path}: {issue.message}")

            # Phase 5: Refine tree based on judge feedback
            print(f"  Refining tree based on feedback...")
            tree = refine_tree(tree, semantic_review, ref_data, cost_tracker)

            # Print refined tree
            print(f"  Refined tree:")
            _print_tree(tree.root)

            # Re-run structural validation on refined tree
            structural_errors = validate_tree_structure(tree, ref_data, args.max_depth, args.max_breadth)
            error_count = sum(1 for e in structural_errors if e.severity == "error")
            warn_count = sum(1 for e in structural_errors if e.severity == "warning")
            if error_count == 0 and warn_count == 0:
                print(f"  Structural validation   \u2713 passed (post-refinement)")
            else:
                print(f"  Structural validation   {error_count} error(s), {warn_count} warning(s) (post-refinement)")
                for issue in structural_errors:
                    print(f"    [{issue.severity}] {issue.node_path}: {issue.message}")

            # Re-run semantic judge on refined tree
            semantic_review = run_semantic_judge(tree, cost_tracker)
            if semantic_review.status == "pass":
                print(f"  Semantic judge (final)  \u2713 passed")
            else:
                print(f"  Semantic judge (final)  \u26a0 {len(semantic_review.issues)} remaining issue(s)")
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
    print(f"  Saved JSON: {json_path}")

    # Cost line
    print(f"\n{cost_tracker.format_cost_line()}")
    total_nodes = tree.count_nodes()
    max_d = tree.max_depth()
    print(f"Summary: {total_nodes} requirements generated ({max_d} levels), "
          f"{error_count} errors, {warn_count} warnings")
    print(f"\nTo export all results to xlsx:  reqdecomp --export-only")

    return tree


HELP_TEXT = """
  Requirements Decomposition System (reqdecomp)
  ──────────────────────────────────────────────
  Decomposes high-level shipbuilding DIGs into multi-level formal "shall"
  requirements using LLMs. Each DIG becomes a tree of requirements across
  up to 4 levels (Ship → Major System → Subsystem → Equipment), with
  V&V data, a semantic judge review, and automatic refinement.

  Install:
    git clone https://github.com/jude-sph/Requirements.git
    cd Requirements
    pip install -e .

  First-time setup:
    reqdecomp --setup                          Pick a model and enter API keys

  Commands:
    reqdecomp --dig 9584                       Process one DIG
    reqdecomp --dig 9584,9646,9742             Process multiple DIGs
    reqdecomp --all                            Process all DIGs in the workbook
    reqdecomp --export-only                    Export JSON results to xlsx
    reqdecomp --setup                          Change model or API keys
    reqdecomp --dry-run --all                  Estimate cost before running

  Cost control:
    reqdecomp --dig 9584 --max-depth 2         Fewer levels (cheaper)
    reqdecomp --dig 9584 --max-breadth 1       Fewer branches (cheaper)
    reqdecomp --dig 9584 --skip-vv             Skip V&V generation (faster)
    reqdecomp --dig 9584 --skip-judge          Skip judge + refinement (faster)

  Input:
    Place GTR-SDS.xlsx in the current directory, or use --input /path/to/file.xlsx

  Output:
    output/json/     Per-DIG JSON trees (source of truth)
    output/xlsx/     Exported spreadsheet
    output/logs/     Detailed run logs
"""


def main():
    parser = argparse.ArgumentParser(
        prog="reqdecomp",
        description=HELP_TEXT,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--dig", type=str, help="Process DIG(s) by DNG ID (comma-separated for multiple: 9584,9646)")
    group.add_argument("--all", action="store_true", help="Process all DIGs")
    group.add_argument("--export-only", action="store_true", help="Export existing JSON results to xlsx")
    group.add_argument("--setup", action="store_true", help="Configure model and API keys interactively")

    parser.add_argument("--max-depth", type=int, default=DEFAULT_MAX_DEPTH, help=f"Max decomposition depth, 1-4 (default: {DEFAULT_MAX_DEPTH})")
    parser.add_argument("--max-breadth", type=int, default=DEFAULT_MAX_BREADTH, help=f"Max children per node (default: {DEFAULT_MAX_BREADTH})")
    parser.add_argument("--skip-vv", action="store_true", help="Skip V&V generation (faster, cheaper)")
    parser.add_argument("--skip-judge", action="store_true", help="Skip semantic judge and refinement")
    parser.add_argument("--verbose", action="store_true", help="Show detailed debug output")
    parser.add_argument("--dry-run", action="store_true", help="Estimate API calls and cost without running")
    parser.add_argument("--force", action="store_true", help="Reprocess DIGs that already have output")
    parser.add_argument("--input", type=str, default=None, help="Path to input xlsx (default: ./GTR-SDS.xlsx in current directory)")

    args = parser.parse_args()

    # Setup mode (no logging needed)
    if args.setup:
        import subprocess
        subprocess.run([sys.executable, str(Path(__file__).parent.parent / "scripts" / "configure.py")])
        return

    setup_logging(args.verbose)

    # Validate provider + model compatibility
    from src.config import PROVIDER
    if PROVIDER == "openrouter" and not MODEL.startswith(("anthropic/", "google/", "openai/", "deepseek/", "meta-llama/")):
        print(f"Error: Model '{MODEL}' doesn't look like an OpenRouter model ID.")
        print(f"  Your .env has PROVIDER=openrouter but MODEL={MODEL}")
        print()
        print("  OpenRouter model IDs look like: anthropic/claude-sonnet-4, google/gemini-2.5-flash")
        print("  Run 'reqdecomp --setup' to fix this, or change PROVIDER=anthropic in your .env")
        sys.exit(1)

    xlsx_path = Path(args.input) if args.input else XLSX_PATH

    # Check xlsx exists (except for export-only which doesn't need it)
    if not args.export_only and not xlsx_path.exists():
        print(f"Error: Input file not found: {xlsx_path}")
        print()
        print("Place your GTR-SDS.xlsx in the current directory, or specify a path:")
        print(f"  reqdecomp --dig 9584 --input /path/to/your-file.xlsx")
        sys.exit(1)

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
        total_reqs = sum(t.count_nodes() for t in trees)
        print(f"Exported {len(trees)} DIGs ({total_reqs} requirements) to:")
        print(f"  {output_path}")
        return

    # Load workbook
    ref_data = load_workbook_data(xlsx_path)

    # Parse DIG IDs (supports comma-separated: --dig 9584,9646,9742)
    dig_ids = []
    if args.dig:
        dig_ids = [d.strip() for d in args.dig.split(",") if d.strip()]
        missing = [d for d in dig_ids if d not in ref_data.digs]
        if missing:
            print(f"Error: DIG(s) not found in workbook: {', '.join(missing)}")
            sys.exit(1)

    # Dry run
    if args.dry_run:
        n = len(ref_data.digs) if args.all else len(dig_ids)
        max_nodes = sum(args.max_breadth ** i for i in range(args.max_depth))
        calls_per_dig = max_nodes * 2 + 1
        if args.skip_vv:
            calls_per_dig = max_nodes + 1
        if args.skip_judge:
            calls_per_dig -= 1
        print(f"Dry run: {n} DIGs, max {calls_per_dig} API calls/DIG, max {n * calls_per_dig} total calls")
        return

    # Single or multi-DIG mode
    if dig_ids:
        cost_tracker = CostTracker(model=MODEL)
        trees = []
        for i, dig_id in enumerate(dig_ids, 1):
            if len(dig_ids) > 1:
                print(f"\n[{i}/{len(dig_ids)}]", end="")
            dig = ref_data.digs[dig_id]
            tree = process_dig(dig["dig_id"], dig["dig_text"], ref_data, args, cost_tracker)
            trees.append(tree)

        # Auto-export to xlsx if multiple DIGs
        if len(trees) > 1:
            OUTPUT_XLSX_DIR.mkdir(parents=True, exist_ok=True)
            output_path = OUTPUT_XLSX_DIR / "results.xlsx"
            export_trees_to_xlsx(trees, output_path)
            total_reqs = sum(t.count_nodes() for t in trees)
            print(f"\nExported {len(trees)} DIGs ({total_reqs} requirements) to:")
            print(f"  {output_path}")
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
        print(f"\nOutput:")
        print(f"  JSON:  {OUTPUT_JSON_DIR} ({total} files)")
        print(f"  XLSX:  {output_path}")
        print(f"  Logs:  {OUTPUT_LOGS_DIR}")


if __name__ == "__main__":
    main()
