"""OpenAI Agents SDK implementation of the Interpreter Agent."""

from __future__ import annotations

import inspect
import os
from collections.abc import Awaitable, Callable
from typing import Any

from .contracts import MealRequestCandidateV2
from .prompts import INTERPRETER_INSTRUCTIONS


DEFAULT_INTERPRETER_MODEL = "gpt-5.6-sol"


class AgentSdkUnavailableError(RuntimeError):
    """Raised when the OpenAI Agents SDK dependency is unavailable."""


class InterpreterRunError(RuntimeError):
    """Raised after the bounded SDK retry is exhausted."""


def build_interpreter_agent(model: str | None = None) -> Any:
    """Construct the focused SDK agent with a Pydantic structured output."""

    try:
        from agents import Agent
    except ImportError as exc:  # pragma: no cover - exercised only in bad installs
        raise AgentSdkUnavailableError(
            "Install the project dependencies so `openai-agents` is available."
        ) from exc

    return Agent(
        name="Group Meal Request Interpreter",
        instructions=INTERPRETER_INSTRUCTIONS,
        model=model or os.getenv("GROUP_FOOD_INTERPRETER_MODEL", DEFAULT_INTERPRETER_MODEL),
        output_type=MealRequestCandidateV2,
    )


RunnerCallable = Callable[..., Awaitable[Any]]


class MealRequestInterpreter:
    """Bounded wrapper around ``agents.Runner.run``.

    The first run and one retry use the same complete raw text. Structured-output
    validation and any model turns remain visible in the Agents SDK trace.
    """

    def __init__(
        self,
        *,
        model: str | None = None,
        runner: RunnerCallable | None = None,
        maximum_attempts: int = 2,
        run_config: Any | None = None,
    ) -> None:
        if maximum_attempts not in (1, 2):
            raise ValueError("maximum_attempts must be 1 or 2")
        self.agent = build_interpreter_agent(model)
        self.maximum_attempts = maximum_attempts
        if run_config is None:
            from agents import RunConfig

            run_config = RunConfig(
                workflow_name="group_food_request_interpreter",
                trace_include_sensitive_data=False,
            )
        self._run_config = run_config
        if runner is None:
            from agents import Runner

            runner = Runner.run
        self._runner = runner

    async def interpret(self, raw_text: str) -> MealRequestCandidateV2:
        last_error: Exception | None = None
        for _attempt in range(1, self.maximum_attempts + 1):
            try:
                result = self._runner(
                    self.agent,
                    raw_text,
                    max_turns=4,
                    run_config=self._run_config,
                )
                if inspect.isawaitable(result):
                    result = await result
                output = result.final_output
                if isinstance(output, MealRequestCandidateV2):
                    return output
                return MealRequestCandidateV2.model_validate(output)
            except Exception as exc:  # the caller receives one bounded failure
                last_error = exc
        raise InterpreterRunError(
            f"Interpreter Agent failed after {self.maximum_attempts} attempt(s): "
            f"{type(last_error).__name__}"
        ) from last_error
