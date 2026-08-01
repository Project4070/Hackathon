# Analysis 005

## Evidence window

Attempts 001-005. The repository baseline before these attempts was `60 passed`; attempt 001 used the reviewed offline fixture and attempts 002-005 used live CLI input without a process-level API key.

## Repeated blockers

- `missing_process_api_key` repeated on all three valid natural-language prompts and the injection-mixed valid prompt. It blocks before G2 and prevents any live model, semantic, menu, or planner evidence.
- G9 is blocked on both paths: valid live failures produce no trace, while the offline success trace does not contain a machine-readable final CLI payload for exact comparison.
- Attempt 005 exposed a split behavior: the direct preflight returns `prompt_injection_text_ignored` as a warning, but the live CLI does not persist that warning before its configuration failure.

## Prompt versus system diagnosis

The three-language repetition (Korean, English, mixed) points to an environment/system blocker, not prompt overfitting. The canonical fixture passes G1-G8 deterministically but is fixture-only and bypasses live interpretation. No claim about live Interpreter quality is justified.

The injection case is not a prompt failure: preflight treats the text as untrusted data and warns. The missing evidence is caused by trace ordering and the unavailable process key.

## Data and dependency observations

- The reviewed snapshot is usable in offline mode and is explicitly synthetic/reviewed, not live pricing or availability.
- Location, budget, allergy, and menu-snapshot behavior cannot be tested from natural language until G2 is reachable.
- Existing pre-run traces show prior G3 failures but do not include attempt metadata, so they are useful context rather than comparable trials.

## Expected improvement and regression risk

1. Create the local trace writer and emit G1/preflight plus configuration status before requiring the API key. Expected: every blocked run becomes auditable and G9 can distinguish environment failure from input failure. Risk: accidentally logging sensitive input; keep only hashes, lengths, issue codes, and redacted values.
2. Add a deterministic `--offline-text`/fixture-interpreter mode that runs the actual raw text through G1-G3 and a trusted candidate fixture without external calls. Expected: language/validation holdouts become testable offline. Risk: falsely presenting fixture extraction as model quality; label the mode explicitly.
3. Preserve the structured terminal outcome taxonomy in the CLI (`external_dependency_blocked` versus `request_rejected`) instead of only a generic configuration message. Expected: better judge-visible diagnosis. Risk: compatibility changes for scripts expecting exit code 3 only.
4. Add a CLI/trace correlation record containing the final display/failure artifact ID and a hash of the redacted result. Expected: G9 exact consistency checks. Risk: hash schema drift; version the record.
5. Keep prompt content stable until the key/external condition is resolved. Expected: avoids overfitting and wasted calls. Risk: less immediate demonstration of model language coverage.

## Next five attempts

- Run injection/absurd/oversized/unknown-food preflight holdouts without model calls and verify no downstream tool event.
- Run tiny-budget and missing-location valid requests only once each; classify their current pre-G2 environment block, not their semantic behavior.
- Run offline missing-snapshot to exercise G5-G8 deterministic gateway block.
- Run offline restaurant-change/feedback rehearsal to exercise recomputation rather than copied quantities.
- After the external key is available, rerun the three language prompts unchanged before changing any prompt wording.

## Reasons not to apply yet

Do not weaken preflight, auto-fill missing location, invent menu facts, or route around the structured-output contract to get a live-looking plan. Those changes would improve apparent pass rate while violating the safety boundary.
