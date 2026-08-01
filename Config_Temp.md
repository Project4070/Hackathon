# Serving-Demand Configuration (JSON-Compatible)

> Temporary product policy note: when a user omits a budget, the current
> validator applies `12,000 KRW/person` as a hard ceiling. This is a hackathon
> default only and is intentionally replaceable/removable.

Status: calculator compatibility baseline. The filename is historical; do not treat the values as disposable. Rename it together with implementation imports when the shared configuration module is created.

The existing constant names, keys, and factor values are preserved for
compatibility with the calculation functions. Decimal values are stored as
strings and must be loaded with `Decimal`.

```json
{
  "APPETITE_FACTORS": {
    "very_low": "0.55",
    "low": "0.75",
    "normal": "1.00",
    "high": "1.30",
    "very_high": "1.60"
  },
  "MEAL_FACTORS": {
    "breakfast": "0.80",
    "lunch": "0.95",
    "dinner": "1.00",
    "late_night_snack": "0.65",
    "snack": "0.40",
    "only_meal_during_event": "1.10"
  },
  "MARGIN_FACTORS": {
    "minimize_leftovers": "0.04",
    "balanced": "0.08",
    "avoid_shortage": "0.11"
  },
  "ADJUSTMENT_FACTORS": {
    "after_exercise": "1.15",
    "after_long_activity": "1.10",
    "very_hungry": "1.10",
    "low_appetite": "0.75",
    "ate_1_to_2_hours_ago": "0.55",
    "ate_3_to_4_hours_ago": "0.85",
    "just_ate": "0.35"
  },
  "PERSON_SERVING_MAXIMUMS": {
    "breakfast": "1.60",
    "lunch": "2.00",
    "dinner": "2.00",
    "late_night_snack": "1.30",
    "snack": "0.90",
    "only_meal_during_event": "2.20"
  },
  "MAX_TOTAL_MARGIN": "0.15",
  "ADJUSTMENT_CATEGORIES": {
    "after_exercise": "activity",
    "after_long_activity": "activity",
    "very_hungry": "hunger",
    "low_appetite": "hunger",
    "ate_1_to_2_hours_ago": "previous_meal",
    "ate_3_to_4_hours_ago": "previous_meal",
    "just_ate": "previous_meal"
  },
  "MUTUALLY_EXCLUSIVE_ADJUSTMENTS": [
    ["just_ate", "ate_1_to_2_hours_ago"],
    ["just_ate", "ate_3_to_4_hours_ago"],
    ["ate_1_to_2_hours_ago", "ate_3_to_4_hours_ago"],
    ["very_hungry", "low_appetite"]
  ],
  "POTENTIAL_DOUBLE_COUNT_ADJUSTMENTS": [
    ["after_exercise", "very_hungry"],
    ["after_long_activity", "very_hungry"]
  ]
}
```

## Python loading rules

- Convert the values of `APPETITE_FACTORS`, `MEAL_FACTORS`, `MARGIN_FACTORS`,
  `ADJUSTMENT_FACTORS`, and `PERSON_SERVING_MAXIMUMS` to `Decimal`.
- Convert `MAX_TOTAL_MARGIN` to `Decimal`.
- Convert each inner array in `MUTUALLY_EXCLUSIVE_ADJUSTMENTS` and
  `POTENTIAL_DOUBLE_COUNT_ADJUSTMENTS` to `frozenset`, and the outer collection
  to `set`.
- Do not rename or regroup any of these keys in the compatibility loader.

## Contract adapter aliases

The external contract remains domain-oriented while the existing calculator retains its current keys:

| Planning contract | Calculator configuration |
| --- | --- |
| `very_light` | `very_low` |
| `light` | `low` |
| `normal` | `normal` |
| `large` | `high` |
| `very_large` | `very_high` |
| `late_night` | `late_night_snack` |
| `minimize_shortage` | `avoid_shortage` |

Implement these translations in versioned deterministic adapter code, not in the Interpreter Agent prompt. The adapter must reject unknown values, preserve custom milli-serving values, and record every applied alias. Adjustment codes are applied only when the validated contract fields and evidence support the exact meaning; no deterministic component may reinterpret raw prose.
