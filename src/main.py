# src/main.py
import argparse
import json
import logging
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
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

    file_handler = logging.FileHandler(log_file, encoding="utf-8")
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


def _count_phases(args) -> int:
    """Count the number of pipeline phases for progress bar."""
    phases = 1  # decomposition always runs
    if not args.skip_vv:
        phases += 1
    phases += 1  # structural validation
    if not args.skip_judge:
        phases += 3  # judge + refine + final judge
    phases += 1  # save
    return phases


def process_dig(
    dig_id: str,
    dig_text: str,
    ref_data,
    args,
    cost_tracker: CostTracker,
) -> RequirementTree:
    """Process a single DIG through the full pipeline."""
    from tqdm import tqdm

    total_phases = _count_phases(args)
    desc_width = 50
    print(f"\nDIG {dig_id}: \"{dig_text[:60]}...\"")

    # Suppress console logging during progress bar (logs still go to file)
    src_logger = logging.getLogger("src")
    console_handlers = [h for h in src_logger.handlers if isinstance(h, logging.StreamHandler) and not isinstance(h, logging.FileHandler)]
    for h in console_handlers:
        h.setLevel(logging.CRITICAL)

    pbar = tqdm(total=total_phases, bar_format="  {l_bar}{bar}| {n_fmt}/{total_fmt} [{elapsed}<{remaining}]", leave=True)

    # Phase 1: Decomposition
    pbar.set_description("Decomposing".ljust(desc_width))
    tree = decompose_dig(
        dig_id=dig_id,
        dig_text=dig_text,
        ref_data=ref_data,
        max_depth=args.max_depth,
        max_breadth=args.max_breadth,
        skip_vv=args.skip_vv,
        cost_tracker=cost_tracker,
    )
    pbar.update(1)

    if not tree.root:
        pbar.set_description("No requirements generated".ljust(desc_width))
        pbar.close()
        return tree

    nodes = tree.count_nodes()
    pbar.set_description(f"Decomposed: {nodes} requirements".ljust(desc_width))

    # Phase 2: V&V
    if not args.skip_vv:
        pbar.set_description(f"Generating V&V for {nodes} requirements".ljust(desc_width))
        apply_vv_to_tree(tree, ref_data, cost_tracker)
        pbar.update(1)

    # Phase 3: Structural validation
    pbar.set_description("Structural validation".ljust(desc_width))
    structural_errors = validate_tree_structure(tree, ref_data, args.max_depth, args.max_breadth)
    error_count = sum(1 for e in structural_errors if e.severity == "error")
    warn_count = sum(1 for e in structural_errors if e.severity == "warning")
    pbar.update(1)

    # Phase 4: Semantic judge + refinement loop
    semantic_review = None
    if not args.skip_judge:
        pbar.set_description("Semantic judge reviewing tree".ljust(desc_width))
        semantic_review = run_semantic_judge(tree, cost_tracker)
        pbar.update(1)

        if semantic_review.status != "pass":
            pbar.set_description(f"Refining tree ({len(semantic_review.issues)} issues)".ljust(desc_width))
            tree = refine_tree(tree, semantic_review, ref_data, cost_tracker)

            # Re-validate
            structural_errors = validate_tree_structure(tree, ref_data, args.max_depth, args.max_breadth)
            error_count = sum(1 for e in structural_errors if e.severity == "error")
            warn_count = sum(1 for e in structural_errors if e.severity == "warning")
        pbar.update(1)

        pbar.set_description("Final judge review".ljust(desc_width))
        semantic_review = run_semantic_judge(tree, cost_tracker)
        pbar.update(1)

    # Save
    pbar.set_description("Saving results".ljust(desc_width))
    tree.validation = ValidationResult(
        structural_errors=structural_errors,
        semantic_review=semantic_review,
    )
    tree.cost = cost_tracker.get_summary()

    OUTPUT_JSON_DIR.mkdir(parents=True, exist_ok=True)
    json_path = OUTPUT_JSON_DIR / f"{dig_id}.json"
    json_path.write_text(tree.model_dump_json(indent=2), encoding="utf-8")
    pbar.update(1)
    pbar.set_description("Done".ljust(desc_width))
    pbar.close()

    # Restore console logging
    for h in console_handlers:
        h.setLevel(logging.DEBUG if args.verbose else logging.INFO)

    # Print results
    print()
    _print_tree(tree.root)

    if error_count == 0 and warn_count == 0:
        print(f"  Structural validation   \u2713 passed")
    else:
        print(f"  Structural validation   {error_count} error(s), {warn_count} warning(s)")
        for issue in structural_errors:
            print(f"    [{issue.severity}] {issue.node_path}: {issue.message}")

    if semantic_review:
        if semantic_review.status == "pass":
            print(f"  Semantic judge          \u2713 passed")
        else:
            print(f"  Semantic judge          \u26a0 {len(semantic_review.issues)} remaining issue(s)")
            for issue in semantic_review.issues:
                print(f"    [{issue.severity}] {issue.node_path}: {issue.message}")

    print(f"  Saved: {json_path}")
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
    reqdecomp --web                            Launch web interface in browser
    reqdecomp --web --port 3000                Web interface on custom port

  Cost control:
    reqdecomp --dig 9584 --max-depth 2         Fewer levels (cheaper)
    reqdecomp --dig 9584 --max-breadth 1       Fewer branches (cheaper)
    reqdecomp --dig 9584 --skip-vv             Skip V&V generation (faster)
    reqdecomp --dig 9584 --skip-judge          Skip judge + refinement (faster)

  Performance:
    reqdecomp --all --workers 8                Process 8 DIGs in parallel (default: 4)

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
    group.add_argument("--web", action="store_true", help="Launch web interface in browser")

    parser.add_argument("--port", type=int, default=8000, help="Port for web interface (default: 8000)")
    parser.add_argument("--workers", type=int, default=4, help="Parallel workers for batch processing (default: 4)")
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

    if args.web:
        from src.web.app import start_server
        start_server(port=args.port)
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
            trees.append(RequirementTree.model_validate_json(jf.read_text(encoding="utf-8")))
        OUTPUT_XLSX_DIR.mkdir(parents=True, exist_ok=True)
        output_path = OUTPUT_XLSX_DIR / "results.xlsx"
        export_trees_to_xlsx(trees, output_path)
        total_reqs = sum(t.count_nodes() for t in trees)
        print(f"Exported {len(trees)} DIGs ({total_reqs} requirements) to:")
        print(f"  {output_path}")
        return

    # Load workbook (suppress loader's console logging for clean output)
    src_logger = logging.getLogger("src")
    console_handlers = [h for h in src_logger.handlers if isinstance(h, logging.StreamHandler) and not isinstance(h, logging.FileHandler)]
    for h in console_handlers:
        h.setLevel(logging.CRITICAL)
    print(f"Loading {xlsx_path.name}...", end=" ", flush=True)
    ref_data = load_workbook_data(xlsx_path)
    print(f"{len(ref_data.digs)} DIGs found.")
    for h in console_handlers:
        h.setLevel(logging.DEBUG if args.verbose else logging.INFO)

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

    # Single DIG mode (detailed progress)
    if dig_ids and len(dig_ids) == 1:
        cost_tracker = CostTracker(model=MODEL)
        dig = ref_data.digs[dig_ids[0]]
        tree = process_dig(dig["dig_id"], dig["dig_text"], ref_data, args, cost_tracker)
        OUTPUT_XLSX_DIR.mkdir(parents=True, exist_ok=True)
        export_trees_to_xlsx([tree], OUTPUT_XLSX_DIR / "results.xlsx")
        print(f"\nExported 1 DIG(s) ({tree.count_nodes()} requirements) to:")
        print(f"  {OUTPUT_XLSX_DIR / 'results.xlsx'}")
        return

    # Multi-DIG or batch mode (parallel processing)
    if dig_ids or args.all:
        start_time = time.time()
        workers = args.workers

        # Build list of DIGs to process
        if args.all:
            all_dig_ids = list(ref_data.digs.keys())
        else:
            all_dig_ids = dig_ids

        # Separate: already done vs need processing
        to_process = []
        pre_loaded = {}
        for dig_id in all_dig_ids:
            json_path = OUTPUT_JSON_DIR / f"{dig_id}.json"
            if json_path.exists() and not args.force:
                pre_loaded[dig_id] = RequirementTree.model_validate_json(json_path.read_text(encoding="utf-8"))
            else:
                to_process.append(dig_id)

        if pre_loaded:
            print(f"Skipping {len(pre_loaded)} DIGs with existing output (use --force to reprocess)")

        total = len(to_process)
        if total == 0:
            print("All DIGs already processed.")
            trees = [pre_loaded[d] for d in all_dig_ids if d in pre_loaded]
        else:
            print(f"Processing {total} DIGs with {min(workers, total)} parallel workers...\n")
            from tqdm import tqdm
            batch_tracker = CostTracker(model=MODEL)
            completed_trees = {}

            def _process_one(dig_id):
                """Process a single DIG (runs in thread pool)."""
                dig = ref_data.digs[dig_id]
                tracker = CostTracker(model=MODEL)

                tree = decompose_dig(
                    dig_id=dig_id, dig_text=dig["dig_text"], ref_data=ref_data,
                    max_depth=args.max_depth, max_breadth=args.max_breadth,
                    skip_vv=args.skip_vv, cost_tracker=tracker,
                )
                if not tree.root:
                    return dig_id, tree, tracker

                if not args.skip_vv:
                    apply_vv_to_tree(tree, ref_data, tracker)

                structural_errors = validate_tree_structure(tree, ref_data, args.max_depth, args.max_breadth)

                semantic_review = None
                if not args.skip_judge:
                    semantic_review = run_semantic_judge(tree, tracker)
                    if semantic_review.status != "pass":
                        tree = refine_tree(tree, semantic_review, ref_data, tracker)
                        structural_errors = validate_tree_structure(tree, ref_data, args.max_depth, args.max_breadth)
                        semantic_review = run_semantic_judge(tree, tracker)

                tree.validation = ValidationResult(structural_errors=structural_errors, semantic_review=semantic_review)
                tree.cost = tracker.get_summary()

                OUTPUT_JSON_DIR.mkdir(parents=True, exist_ok=True)
                json_path = OUTPUT_JSON_DIR / f"{dig_id}.json"
                json_path.write_text(tree.model_dump_json(indent=2), encoding="utf-8")

                return dig_id, tree, tracker

            pbar = tqdm(total=total, bar_format="  {l_bar}{bar}| {n_fmt}/{total_fmt} [{elapsed}<{remaining}]")

            with ThreadPoolExecutor(max_workers=min(workers, total)) as executor:
                futures = {executor.submit(_process_one, did): did for did in to_process}
                for future in as_completed(futures):
                    try:
                        dig_id, tree, tracker = future.result()
                        completed_trees[dig_id] = tree
                        summary = tracker.get_summary()
                        for entry in summary.breakdown:
                            batch_tracker.record(entry.call_type, entry.level, entry.input_tokens, entry.output_tokens)
                        nodes = tree.count_nodes()
                        pbar.set_description(f"DIG {dig_id}: {nodes} nodes, ${summary.total_cost_usd:.4f}")
                        pbar.update(1)
                    except Exception as e:
                        pbar.set_description(f"DIG {futures[future]}: ERROR")
                        pbar.update(1)
                        logger.error(f"DIG {futures[future]} failed: {e}")

            pbar.close()

            # Merge results in original order
            trees = []
            for dig_id in all_dig_ids:
                if dig_id in pre_loaded:
                    trees.append(pre_loaded[dig_id])
                elif dig_id in completed_trees:
                    trees.append(completed_trees[dig_id])

        # Export
        OUTPUT_XLSX_DIR.mkdir(parents=True, exist_ok=True)
        output_path = OUTPUT_XLSX_DIR / "results.xlsx"
        export_trees_to_xlsx(trees, output_path)

        elapsed = time.time() - start_time
        minutes = int(elapsed // 60)
        seconds = int(elapsed % 60)

        if total > 0:
            summary = batch_tracker.get_summary()
            total_nodes = sum(t.count_nodes() for t in trees)
            print(f"\n{'=' * 40}")
            print(f"Batch Complete")
            print(f"{'=' * 40}")
            print(f"DIGs processed: {len(trees)} ({total} new, {len(pre_loaded)} cached)")
            print(f"Total requirements: {total_nodes}")
            print(f"Total API calls: {summary.api_calls}")
            print(f"Total tokens: {summary.total_input_tokens:,} input / {summary.total_output_tokens:,} output")
            print(f"Total cost: ${summary.total_cost_usd:.2f}")
            print(f"Time elapsed: {minutes}m {seconds}s")
            print(f"Workers: {min(workers, total)}")
            print(f"\nOutput:")
            print(f"  JSON:  {OUTPUT_JSON_DIR} ({len(trees)} files)")
            print(f"  XLSX:  {output_path}")
            print(f"  Logs:  {OUTPUT_LOGS_DIR}")
        print(f"  Logs:  {OUTPUT_LOGS_DIR}")


if __name__ == "__main__":
    main()
