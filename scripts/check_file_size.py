"""Fail if a production module exceeds the line budget."""

from __future__ import annotations

import sys
from pathlib import Path

MAX_LINES = 250
ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src" / "automator"
ALLOWLIST = {
    "src/automator/ui/main_window.py",
    "src/automator/config.py",
    "src/automator/domain/parser.py",
}


def _line_count(path: Path) -> int:
    return sum(1 for _ in path.open(encoding="utf-8"))


def main() -> int:
    failures: list[str] = []
    stale: list[str] = []
    seen_allowlist: set[str] = set()
    for path in sorted(SRC.rglob("*.py")):
        relative = path.relative_to(ROOT).as_posix()
        lines = _line_count(path)
        if relative in ALLOWLIST:
            seen_allowlist.add(relative)
            if lines <= MAX_LINES:
                stale.append(f"{relative}: {lines} (allowlisted, now under {MAX_LINES})")
            continue
        if lines > MAX_LINES:
            failures.append(f"{relative}: {lines} lines (limit {MAX_LINES})")
    missing = sorted(ALLOWLIST - seen_allowlist)
    if missing:
        failures.extend(f"allowlist entry missing: {name}" for name in missing)
    if stale:
        failures.extend(stale)
    if not failures:
        return 0
    print("File size check failed:", file=sys.stderr)
    for item in failures:
        print(f"  {item}", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
