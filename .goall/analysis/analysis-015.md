# Analysis 015

## Final evidence window

Fifteen attempts were recorded. No source or prompt code was changed during the run. Verification after the holdouts: `60 passed`, 23 schemas generated, `pip check` clean, and 23 focused crawler/serving/planner holdout tests passed.

## Gate summary

The counts below are attempt-level, strict evidence counts. `not_run` is not treated as a pass. Some controlled blocked terminal results are counted as G8 evidence of explicit blocking, not as successful plans.

| Gate | Pass | Fail/blocked | Not run | Meaning |
|---|---:|---:|---:|---|
| G1 raw preflight | 13 | 0 | 2 | Includes warning-only injection handling and rejected absurd values |
| G2 structured interpreter | 4 | 0 | 11 | Four fixture/simulated-path passes; zero live model passes |
| G3 profile validation | 4 | 0 | 11 | Fixture/deterministic only |
| G4 serving | 4 | 0 | 11 | Fixture/deterministic only |
| G5 snapshot/gateway | 3 | 1 | 11 | Missing snapshot exposed a typed-error classification gap |
| G6 enrichment/eligibility | 3 | 0 | 12 | Fixture/deterministic only |
| G7 combination/ranking/final validation | 3 | 0 | 12 | Fixture/deterministic only |
| G8 plan or explicit blocked output | 13 | 0 | 2 | Four plans plus controlled blocked outcomes; not 13 successful plans |
| G9 trace/CLI consistency | 5 | 9 | 1 | Partial/path evidence exists; exact result hash is missing |

The more decision-relevant eligible-run rates are: G2-G4 `4/4` on runs that reached them; G5 `3/4`; G6-G7 `3/3`; G9 exact consistency `0/15` because no exact result-hash check exists. These rates do not support a live-success claim.

## Most frequent blocker

`missing_process_api_key` occurred in attempts 002-005 and 008-010: seven live semantic holdouts, including Korean, English, mixed, unknown-food, tiny-budget, missing-location, and injection-mixed requests. It prevented G2 and all downstream live evaluation. The existing `.env` contains a non-empty key entry, but the process environment does not; the application intentionally does not auto-load `.env`.

Secondary blocker: G9 trace/CLI reconciliation is incomplete. The offline path writes trace events and the CLI writes a plan, but there is no shared terminal-result hash/artifact record. Missing snapshot also leaks `KeyError` into a generic blocked diagnostic.

## Prompt diagnosis

There is no evidence that a more elaborate prompt is needed. The most reproducible prompt is the canonical 15-person request fixture, hash `sha256:B5B722B8AF45A3999C74632CBECE33BF9A3840BF103F60114770A858F884B009`, but it is fixture-only. The current recommended prompt shape is a concise fact-bearing request with explicit attendance, appetite cohorts, location/time, category, budget scope, restrictions, risk preference, and source-verification request. Keep the Korean, English, and mixed variants semantically equivalent; do not add instruction-heavy text until live extraction is available.

## Fixture-only or live

This run is **fixture-only for all plan-producing paths**. Live execution is **external_dependency_blocked** because no process-level API key was available. It is not correct to call the system live-succeeded.

## System improvements, priority order

1. **Safety and observability:** initialize a privacy-safe trace before dependency checks; emit G1 preflight and a typed external-dependency event without raw text, secrets, tokens, or model payloads.
2. **Gateway correctness:** convert missing/stale/unusable snapshot errors into typed `data_unavailable` or `deterministic_gateway_blocked` outcomes with field, received ID, reason, and corrective action; never expose raw `KeyError`.
3. **G9 consistency:** persist a versioned terminal record containing outcome, display/failure artifact ID, trace path, and a deterministic hash of the redacted presentation payload. Verify the CLI/UI renders the same artifact.
4. **Offline coverage:** add an explicit offline text harness using real G1-G3 plus a declared fixture interpreter candidate, labeled `simulated_structured_output`; never present it as live model evidence.
5. **External readiness:** provision `OPENAI_API_KEY` only in the process environment and rerun the unchanged three language prompts before any prompt edits. Confirm network/model availability and record only key-used boolean.

## Prompt improvements

- Use one compact request with explicit facts rather than narrative filler or meta-instructions.
- Say “if location, restrictions, or source-backed menu data are missing, ask for clarification or return a blocked outcome; do not invent facts.” This is a behavioral request, not a replacement for deterministic validation.
- Keep quantities literal with units; do not ask the model to calculate order quantities.
- Use the same semantic content in Korean, English, and mixed-language holdouts to measure language effects fairly.

## Regression risks and non-actions

Do not auto-load `.env` silently for production behavior, bypass G2, infer allergy safety, invent unknown foods, clamp absurd values, copy quantities across restaurants, or make tiny budgets appear feasible. Those changes could improve apparent pass rate while increasing unsafe-order risk and breaking the AI/deterministic boundary.

## Unresolved external conditions

- Process-level `OPENAI_API_KEY` is absent; `.env` contains a non-empty entry but was not used.
- Live network/API availability and quota/model access are unverified.
- Live restaurant crawl/source freshness is unverified; the canonical snapshot is `simulated_reviewed_fixture`.
- Exact CLI/UI/trace terminal-result equivalence is not implemented.

## Next run

The next `/goall` execution starts at **attempt 016**. First action should be to re-check process-level key/model/network state, then run the unchanged Korean valid prompt; if the key is still unavailable, continue only with offline text-harness or deterministic holdouts and do not mutate normal prompts.
