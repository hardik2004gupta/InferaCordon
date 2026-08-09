"""
Updates README.md metrics table with latest benchmark results.

Reads benchmark JSON output and overwrites the <!-- METRICS --> section
in README.md with a formatted markdown table. Run after each benchmark.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path


def update_readme(benchmark_json_path: str, readme_path: str = "README.md") -> None:
    raise NotImplementedError("Implement per CLAUDE.md Section 20 (Week 9)")


if __name__ == "__main__":
    update_readme(sys.argv[1])
