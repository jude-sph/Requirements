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
PROVIDER = os.getenv("PROVIDER", "anthropic")  # "anthropic" or "openrouter"
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY", "")
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
