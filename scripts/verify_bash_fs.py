#!/usr/bin/env python
"""Bash+FS Subagents Architecture Verification Script.

Verifies that all components of the Bash+FS Subagents architecture are
properly installed and functioning.
"""

import sys
from pathlib import Path


def main() -> int:
    """Run verification and return exit code."""
    print("=" * 60)
    print("GridCode Bash+FS Subagents Architecture - Verification")
    print("=" * 60)
    print()

    errors = []

    # Phase 1: Infrastructure Layer
    print("[Phase 1] Infrastructure Layer")
    print("-" * 40)

    try:
        from grid_code.infrastructure import FileContext

        print("  ✓ FileContext imported")
    except Exception as e:
        errors.append(f"FileContext: {e}")
        print(f"  ✗ FileContext: {e}")

    try:
        from grid_code.infrastructure import SkillLoader

        print("  ✓ SkillLoader imported")
    except Exception as e:
        errors.append(f"SkillLoader: {e}")
        print(f"  ✗ SkillLoader: {e}")

    try:
        from grid_code.infrastructure import Event, EventBus, SubagentEvent

        print("  ✓ EventBus imported")
    except Exception as e:
        errors.append(f"EventBus: {e}")
        print(f"  ✗ EventBus: {e}")

    try:
        from grid_code.infrastructure import PermissionMatrix, SecurityGuard

        print("  ✓ SecurityGuard imported")
    except Exception as e:
        errors.append(f"SecurityGuard: {e}")
        print(f"  ✗ SecurityGuard: {e}")

    print()

    # Phase 3: RegSearch-Subagent
    print("[Phase 3] RegSearch-Subagent")
    print("-" * 40)

    try:
        from grid_code.subagents import RegSearchSubagent

        print("  ✓ RegSearchSubagent imported")

        from grid_code.subagents.config import SUBAGENT_CONFIGS, SubagentType

        cfg = SUBAGENT_CONFIGS[SubagentType.REGSEARCH]
        print(f"  ✓ Config: {cfg.name}, tools: {len(cfg.tools)}")
    except Exception as e:
        errors.append(f"RegSearchSubagent: {e}")
        print(f"  ✗ RegSearchSubagent: {e}")

    print()

    # Phase 4: Coordinator
    print("[Phase 4] Coordinator")
    print("-" * 40)

    try:
        from grid_code.orchestrator import Coordinator

        print("  ✓ Coordinator imported")
    except Exception as e:
        errors.append(f"Coordinator: {e}")
        print(f"  ✗ Coordinator: {e}")

    print()

    # Phase 2: Directory Structure
    print("[Phase 2] Directory Structure")
    print("-" * 40)

    dirs = ["coordinator", "subagents/regsearch", "shared", "skills"]
    for d in dirs:
        p = Path(d)
        if p.exists():
            print(f"  ✓ {d}/")
        else:
            errors.append(f"Missing: {d}/")
            print(f"  ✗ {d}/ (missing)")

    print()
    print("=" * 60)

    if errors:
        print(f"✗ {len(errors)} errors found")
        return 1
    else:
        print("✓ All verification passed")
        return 0


if __name__ == "__main__":
    sys.exit(main())
