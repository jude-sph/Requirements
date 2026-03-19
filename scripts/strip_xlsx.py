# scripts/strip_xlsx.py
"""Strip LLM-generated columns from GTR-SDS.xlsx, keeping only source data."""
from pathlib import Path
from openpyxl import load_workbook

KEEP_COLUMNS = {1, 2}  # A=DNG, B=DIG Text
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
    for col_idx in sorted(STRIP_COLUMNS, reverse=True):
        ws.delete_cols(col_idx)
    print(f"Stripped {len(STRIP_COLUMNS)} columns from Requirements Decomposition tab")
    print(f"Kept: DNG, DIG Text")
    print(f"Reference tabs preserved: {[s.title for s in wb.worksheets if s.title != 'Requirements Decomposition']}")
    wb.save(output_path)
    print(f"Saved: {output_path}")

if __name__ == "__main__":
    main()
