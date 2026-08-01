"""Text-envelope checks that run before the Interpreter Agent.

Preflight verifies only that the request is bounded, readable text. It does not
classify meal intent, supported food categories, numeric values, or instruction-
like content. Those semantic decisions belong to structured interpretation and
deterministic validation downstream.
"""

from __future__ import annotations

from enum import StrEnum

from pydantic import Field

from .contracts import ContractModel, IssueSeverity


class PreflightStatus(StrEnum):
    PASSED = "passed"
    REJECTED = "rejected"


class RawInputLimits(ContractModel):
    max_characters: int = Field(default=5_000, ge=1, le=100_000)


class RawInputIssue(ContractModel):
    code: str = Field(min_length=1, max_length=100, pattern=r"^[a-z0-9_]+$")
    severity: IssueSeverity
    field_path: str = Field(min_length=1, max_length=256, pattern=r"^/.*")
    received_value: str = Field(min_length=1, max_length=300)
    reason: str = Field(min_length=1, max_length=500)
    corrective_action: str = Field(min_length=1, max_length=300)


class RawInputPreflightResult(ContractModel):
    status: PreflightStatus
    input_length: int = Field(ge=0)
    issues: list[RawInputIssue] = Field(max_length=32)


def _issue(
    code: str,
    received_value: str,
    reason: str,
    corrective_action: str,
    *,
    field_path: str = "/raw_input",
    severity: IssueSeverity = IssueSeverity.FATAL,
) -> RawInputIssue:
    return RawInputIssue(
        code=code,
        severity=severity,
        field_path=field_path,
        received_value=received_value[:300],
        reason=reason,
        corrective_action=corrective_action,
    )


def preflight_raw_input(
    raw_text: str,
    limits: RawInputLimits | None = None,
) -> RawInputPreflightResult:
    """Verify the input is bounded, nonempty text without unreadable controls."""

    limits = limits or RawInputLimits()

    if not isinstance(raw_text, str):
        return RawInputPreflightResult(
            status=PreflightStatus.REJECTED,
            input_length=0,
            issues=[
                _issue(
                    "input_not_text",
                    type(raw_text).__name__,
                    "The meal description must be UTF-8 text.",
                    "Send the request as text.",
                )
            ],
        )

    input_length = len(raw_text)
    if input_length > limits.max_characters:
        return RawInputPreflightResult(
            status=PreflightStatus.REJECTED,
            input_length=input_length,
            issues=[
                _issue(
                    "input_too_long",
                    str(input_length),
                    f"The input exceeds the {limits.max_characters}-character limit; it was not truncated.",
                    "Shorten the request and submit it again.",
                )
            ],
        )

    if not raw_text.strip():
        return RawInputPreflightResult(
            status=PreflightStatus.REJECTED,
            input_length=input_length,
            issues=[
                _issue(
                    "input_empty",
                    "empty text",
                    "No readable request text was provided.",
                    "Provide a nonempty text request.",
                )
            ],
        )

    illegal_controls = sorted(
        {ord(character) for character in raw_text if ord(character) < 32 and character not in "\n\r\t"}
    )
    if illegal_controls:
        return RawInputPreflightResult(
            status=PreflightStatus.REJECTED,
            input_length=input_length,
            issues=[
                _issue(
                    "unsupported_control_characters",
                    ",".join(f"U+{value:04X}" for value in illegal_controls),
                    "The text contains unreadable control characters.",
                    "Remove the listed control characters and resubmit.",
                )
            ],
        )

    return RawInputPreflightResult(
        status=PreflightStatus.PASSED,
        input_length=input_length,
        issues=[],
    )
