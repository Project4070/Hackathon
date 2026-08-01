"""Summarize one local Group Food Agent JSONL trace for debugging."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from .tracing import summarize_trace


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("trace_file", type=Path)
    args = parser.parse_args()
    try:
        summary = summarize_trace(args.trace_file)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        parser.exit(2, f"cannot read trace: {exc}\n")
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
