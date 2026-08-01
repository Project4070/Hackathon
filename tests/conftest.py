from __future__ import annotations

import json
from pathlib import Path

import pytest

from group_food_agent.contracts import MealRequestCandidateV2


ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def canonical_raw_text() -> str:
    return (ROOT / "fixtures" / "canonical_15_request.txt").read_text(encoding="utf-8").strip()


@pytest.fixture
def canonical_candidate() -> MealRequestCandidateV2:
    payload = json.loads((ROOT / "fixtures" / "canonical_15_candidate.json").read_text(encoding="utf-8"))
    return MealRequestCandidateV2.model_validate(payload)

