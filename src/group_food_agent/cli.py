"""Minimal live runner for the observable intake pipeline."""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from uuid import uuid4

from .config import load_project_dotenv
from .contracts import LocationRequirementV2, LocationSource
from .pipeline import PipelineEvent, process_meal_request
from .validation import ValidationContextV2


def _event_to_stderr(event: PipelineEvent) -> None:
    print(event.model_dump_json(), file=sys.stderr, flush=True)


async def _run(args: argparse.Namespace) -> int:
    default_location = None
    if args.location:
        default_location = LocationRequirementV2(
            delivery_required=True,
            source=LocationSource.REQUEST_CONTEXT,
            query=args.location,
            latitude=None,
            longitude=None,
        )
    context = ValidationContextV2(
        request_id=args.request_id or f"req_{uuid4().hex}",
        case_id=args.case_id or f"case_{uuid4().hex}",
        default_location=default_location,
    )
    outcome = await process_meal_request(
        args.text,
        context,
        event_sink=_event_to_stderr if args.events else None,
    )
    print(json.dumps(outcome.model_dump(mode="json"), ensure_ascii=False, indent=2))
    return 0 if outcome.status == "ready_for_planning" else 2


def main() -> None:
    load_project_dotenv()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("text", help="Complete natural-language meal request")
    parser.add_argument("--location", help="Trusted request-context delivery location")
    parser.add_argument("--request-id")
    parser.add_argument("--case-id")
    parser.add_argument("--events", action=argparse.BooleanOptionalAction, default=True)
    raise SystemExit(asyncio.run(_run(parser.parse_args())))


if __name__ == "__main__":
    main()
