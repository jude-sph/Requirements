#!/usr/bin/env python3
"""Interactive configuration for the Requirements Decomposition System."""
import os
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent
ENV_PATH = PROJECT_ROOT / ".env"

# Import model catalogue from config (single source of truth)
sys.path.insert(0, str(PROJECT_ROOT))
from src.config import MODEL_CATALOGUE
MODELS = MODEL_CATALOGUE


def load_env() -> dict:
    """Load current .env values."""
    env = {}
    if ENV_PATH.exists():
        for line in ENV_PATH.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                key, _, value = line.partition("=")
                env[key.strip()] = value.strip()
    return env


def save_env(env: dict) -> None:
    """Save env dict to .env file, preserving comments."""
    lines = []
    lines.append("# Requirements Decomposition System Configuration")
    lines.append(f"PROVIDER={env.get('PROVIDER', 'anthropic')}")
    lines.append(f"MODEL={env.get('MODEL', 'claude-sonnet-4-6')}")
    lines.append("")
    ak = env.get("ANTHROPIC_API_KEY", "")
    if ak:
        lines.append(f"ANTHROPIC_API_KEY={ak}")
    ork = env.get("OPENROUTER_API_KEY", "")
    if ork:
        lines.append(f"OPENROUTER_API_KEY={ork}")
    lines.append("")
    ENV_PATH.write_text("\n".join(lines) + "\n", encoding="utf-8")


def show_current(env: dict) -> None:
    """Display current configuration."""
    provider = env.get("PROVIDER", "anthropic")
    model = env.get("MODEL", "claude-sonnet-4-6")
    has_anthro = bool(env.get("ANTHROPIC_API_KEY"))
    has_or = bool(env.get("OPENROUTER_API_KEY"))

    print("\n  Current Configuration:")
    print(f"  Provider:           {provider}")
    print(f"  Model:              {model}")
    print(f"  Anthropic API key:  {'set' if has_anthro else 'not set'}")
    print(f"  OpenRouter API key: {'set' if has_or else 'not set'}")
    print()


def pick_model(env: dict) -> dict:
    """Interactive model picker."""
    print("\n  Available Models:\n")
    print(f"  {'#':<4} {'Model':<35} {'Quality':<12} {'Cost/DIG':<15} {'Speed'}")
    print(f"  {'─'*4} {'─'*35} {'─'*12} {'─'*15} {'─'*10}")

    for i, m in enumerate(MODELS, 1):
        quality = m.get('quality', 'good')
        speed = m.get('speed', 'medium')
        print(f"  {i:<4} {m['name']:<35} {quality:<12} {m['cost_per_dig']:<15} {speed}")

    print()
    total = len(MODELS)
    while True:
        choice = input(f"  Pick a model (1-{total}): ").strip()
        if choice.isdigit() and 1 <= int(choice) <= total:
            break
        print("  Invalid choice. Try again.")

    selected = MODELS[int(choice) - 1]
    env["MODEL"] = selected["id"]
    env["PROVIDER"] = selected["provider"]

    # Check if the required key is set
    if selected["provider"] == "anthropic" and not env.get("ANTHROPIC_API_KEY"):
        print(f"\n  This model requires an Anthropic API key.")
        key = input("  Enter your Anthropic API key (sk-ant-...): ").strip()
        if key:
            env["ANTHROPIC_API_KEY"] = key
    elif selected["provider"] == "openrouter" and not env.get("OPENROUTER_API_KEY"):
        print(f"\n  This model requires an OpenRouter API key.")
        key = input("  Enter your OpenRouter API key (sk-or-...): ").strip()
        if key:
            env["OPENROUTER_API_KEY"] = key

    print(f"\n  Selected: {selected['name']}")
    print(f"  Pricing:  {selected['price']}")
    print(f"  Provider: {selected['provider']}")
    return env


def set_keys(env: dict) -> dict:
    """Set API keys interactively."""
    print("\n  Set API Keys (press Enter to skip/keep current):\n")

    current_anthro = env.get("ANTHROPIC_API_KEY", "")
    masked_anthro = f"...{current_anthro[-8:]}" if len(current_anthro) > 8 else "(not set)"
    key = input(f"  Anthropic API key [{masked_anthro}]: ").strip()
    if key:
        env["ANTHROPIC_API_KEY"] = key

    current_or = env.get("OPENROUTER_API_KEY", "")
    masked_or = f"...{current_or[-8:]}" if len(current_or) > 8 else "(not set)"
    key = input(f"  OpenRouter API key [{masked_or}]: ").strip()
    if key:
        env["OPENROUTER_API_KEY"] = key

    return env


def main():
    env = load_env()

    print("\n  ┌─────────────────────────────────────────┐")
    print("  │  Requirements Decomposition - Setup     │")
    print("  └─────────────────────────────────────────┘")

    show_current(env)

    print("  What would you like to do?\n")
    print("  1) Choose a model")
    print("  2) Set API keys")
    print("  3) Both (full setup)")
    print("  4) Show current config and exit")
    print()

    choice = input("  Choice (1-4): ").strip()

    if choice == "1":
        env = pick_model(env)
    elif choice == "2":
        env = set_keys(env)
    elif choice == "3":
        env = set_keys(env)
        env = pick_model(env)
    elif choice == "4":
        return
    else:
        print("  Invalid choice.")
        return

    save_env(env)
    print(f"\n  Configuration saved to {ENV_PATH}")
    show_current(env)


if __name__ == "__main__":
    main()
