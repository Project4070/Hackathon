"""Run the complete natural-language Group Food Quantity Agent."""

from __future__ import annotations

import argparse
import asyncio
import json
from pathlib import Path
import sys
from uuid import uuid4

from .application import run_group_food_agent
from .config import load_project_dotenv
from .contracts import MealRequestCandidateV2
from .run_payload import build_run_payload
from .validation import ValidationContextV2


class FixtureInterpreter:
    def __init__(self, candidate: MealRequestCandidateV2) -> None:
        self.candidate = candidate

    async def interpret(self, raw_text: str) -> MealRequestCandidateV2:
        return self.candidate


async def _run(args: argparse.Namespace) -> int:
    interpreter = None
    live_planner = True
    raw_text = args.text
    if args.offline_canonical:
        root = Path(__file__).resolve().parents[2]
        raw_text = (root / "fixtures" / "canonical_15_request.txt").read_text(encoding="utf-8")
        candidate = MealRequestCandidateV2.model_validate_json(
            (root / "fixtures" / "canonical_15_candidate.json").read_text(encoding="utf-8")
        )
        interpreter = FixtureInterpreter(candidate)
        live_planner = False
    if not raw_text:
        raise ValueError("provide meal text or use --offline-canonical")
    context = ValidationContextV2(
        request_id=args.request_id or f"request-{uuid4().hex}",
        case_id=args.case_id or f"case-{uuid4().hex}",
    )
    trace_file = args.trace_file
    if args.trace and trace_file is None:
        root = Path(__file__).resolve().parents[2]
        trace_file = root / ".traces" / f"{context.case_id}-{uuid4().hex[:8]}.jsonl"
    run = await run_group_food_agent(
        raw_text,
        context,
        interpreter=interpreter,
        live_planner=live_planner,
        trace_file=trace_file if args.trace else None,
    )
    if run.mode == "live_agents_sdk":
        from agents import flush_traces

        flush_traces()
    execution = run.diagnostics()
    if execution["blocked"]:
        blocked_at = execution["blocked_at"]
        print(
            "[group-food-agent] BLOCKED "
            f"at {blocked_at['source']}"
            f"/{blocked_at.get('tool_name') or blocked_at.get('stage')}: "
            f"{execution['reason']}",
            file=sys.stderr,
        )
    else:
        print(
            "[group-food-agent] SUCCEEDED: validated plan and presentation artifact produced",
            file=sys.stderr,
        )
    payload = build_run_payload(run)
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    if run.plan_result is not None:
        return 0 if run.plan_result.failure is None else 2
    return 0 if run.boundary_outcome.status == "ready_for_planning" else 2


def main() -> None:
    load_project_dotenv()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("text", nargs="?", help="Natural-language meal description")
    parser.add_argument(
        "--offline-canonical",
        "--smoke-success",
        action="store_true",
        help="Run the reviewed successful canonical case without API calls",
    )
    parser.add_argument("--request-id")
    parser.add_argument("--case-id")
    parser.add_argument(
        "--trace",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Write a privacy-conscious local JSONL trace (default: enabled)",
    )
    parser.add_argument(
        "--trace-file",
        type=Path,
        help="JSONL trace path (default: a unique file under .traces)",
    )
    args = parser.parse_args()
    try:
        code = asyncio.run(_run(args))
    except RuntimeError as exc:
        if "OPENAI_API_KEY" not in str(exc):
            raise
        parser.exit(3, f"configuration required: {exc}\n")
    raise SystemExit(code)


if __name__ == "__main__":
    main()
