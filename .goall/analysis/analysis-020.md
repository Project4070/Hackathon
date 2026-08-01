# Analysis 020

## Evidence window

Attempts 016–020 only. No source code or prompt source was modified during this window. The pre-run full test suite was `71 passed`.

## Run summary

| Attempt | Input class | Effective model | Result | Boundary | Tool events |
|---|---|---|---|---|---:|
| 016 | Korean canonical valid request | `gpt-5.6-luna` | `request_rejected` | `interpreter_failure` | 0 |
| 017 | English equivalent valid request | `gpt-5.6-luna` | `request_rejected` | `interpreter_failure` | 0 |
| 018 | Korean/English mixed valid request | `gpt-5.6-luna` | `request_rejected` | `interpreter_failure` | 0 |
| 019 | Injection text plus canonical facts | `gpt-5.6-luna` | `request_rejected` | `interpreter_failure` after G1 warning | 0 |
| 020 | Absurd physical quantity | `gpt-5.6-luna` configured; no model call | `request_rejected` | `unsupported_physical_quantity` at G1 | 0 |

## Gate counts for this window

| Gate | Pass | Blocked/fail | Not run |
|---|---:|---:|---:|
| G1 | 5 | 0 | 0 |
| G2 | 0 | 4 | 1 |
| G3-G7 | 0 | 0 | 5 |
| G8 | 1 explicit rejection | 4 interpreter failures | 0 |
| G9 | 0 exact | 5 partial | 0 |

## Diagnosis

The key was absent from the parent process before CLI launch, but the new CLI entrypoint loaded a non-empty local `.env` entry without overriding process values. The effective model after loading was `gpt-5.6-luna`. Attempts 016–019 reached the OpenAI Agents SDK Interpreter stage and repeatedly emitted a redacted `InterpreterRunError` with `Error getting response`; all four stopped before structured validation and planning. This is an external model/API-response blocker, not evidence of a prompt-quality difference.

Attempt 019 confirms only the local preflight boundary: the injection was treated as untrusted text and recorded as a warning. Because the Interpreter did not return, live model resistance is not established.

Attempt 020 independently confirms the safety gate: the literal `1000 kg` value was preserved, rejected before model/calculator/tool execution, and did not create an extreme order.

## Current claims

- Live Interpreter success: not established (`0/4` valid live holdouts).
- Language comparison: no observed difference; all three valid-language variants share the same external failure boundary.
- Live planner, restaurant lookup, quantity calculation, replan, and feedback: not reached in this window.
- Absurd-mass blocking: reproduced and trace-backed.
- Exact CLI/trace terminal equivalence: still unimplemented; traces contain safe summaries and paths but no terminal result hash.

## Stop condition

Attempt 020 is complete. No further attempt, model call, code change, prompt change, or improvement is made until owner review and approval.
