import os
from pathlib import Path

from dotenv import load_dotenv

# Load .env from current directory first, then package root as fallback
load_dotenv(Path.cwd() / ".env")
load_dotenv(Path(__file__).parent.parent / ".env")

# Paths
PACKAGE_ROOT = Path(__file__).parent.parent  # Where the package is installed
PROMPTS_DIR = PACKAGE_ROOT / "prompts"       # Prompts ship with the package

# Working directory paths (output goes where the user runs the command)
CWD = Path.cwd()
XLSX_PATH = CWD / "GTR-SDS.xlsx"             # Default input location
OUTPUT_JSON_DIR = CWD / "output" / "json"
OUTPUT_XLSX_DIR = CWD / "output" / "xlsx"
OUTPUT_LOGS_DIR = CWD / "output" / "logs"

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
    # Anthropic direct
    "claude-sonnet-4-6": {"input_per_mtok": 3.00, "output_per_mtok": 15.00},
    "claude-opus-4-6": {"input_per_mtok": 15.00, "output_per_mtok": 75.00},
    "claude-haiku-4-5": {"input_per_mtok": 0.80, "output_per_mtok": 4.00},
    # OpenRouter models
    "anthropic/claude-sonnet-4": {"input_per_mtok": 3.00, "output_per_mtok": 15.00},
    "anthropic/claude-haiku-4": {"input_per_mtok": 0.80, "output_per_mtok": 4.00},
    "google/gemini-2.5-flash": {"input_per_mtok": 0.15, "output_per_mtok": 0.60},
    "deepseek/deepseek-chat-v3-0324": {"input_per_mtok": 0.27, "output_per_mtok": 1.10},
    "openai/gpt-4o-mini": {"input_per_mtok": 0.15, "output_per_mtok": 0.60},
}

# Level names
LEVEL_NAMES = {
    1: "Whole Ship",
    2: "Major System",
    3: "Subsystem",
    4: "Equipment",
}
