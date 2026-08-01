# Agent Architecture and Data Workflow

Status: implementation baseline  
Updated: 2026-08-01  
Interactive version: <https://group-food-agent-workflow.thetired3080.chatgpt.site/>

The editable diagram dataset is `workflow-site/public/data/workflow.json`. The web renderer in `workflow-site/app/workflow-diagram.tsx` loads this dataset dynamically; descriptions must remain in the dataset rather than being duplicated in UI code.

## Full Workflow

```mermaid
flowchart TB
  subgraph G1["① 입력 · 전처리 · 해석"]
    U(["사용자 요청<br/>음성 또는 텍스트"])
    TR["transcribe_input<br/>음성 → 텍스트"]
    PF{"preflight_raw_input<br/>기계적 입력 검사"}
    IA("Interpreter Agent<br/>자연어 의미 분류")
    CAND[["MealRequestCandidateV2<br/>후보 코호트 · 근거"]]
    U --> TR --> PF -->|통과| IA --> CAND
  end

  subgraph G2["② 결정적 검증 · 상태"]
    DV{"validate_planning_profile<br/>범위 · 합계 · 충돌 검사"}
    CR(["clarification_required<br/>확인 질문"])
    RJ(["request_rejected<br/>비정상 입력 차단"])
    INTAKE[["PlanningIntakeV2<br/>확정된 사용자 사실"]]
    PCS[("Planning Case Store<br/>case_id · revision")]
    PV[["PlannerViewV2<br/>가벼운 모델용 뷰"]]
    DV -->|모호함| CR
    DV -->|지원 불가| RJ
    DV -->|ready| INTAKE --> PCS --> PV
  end

  CAND --> DV

  subgraph G3["③ Main Planner Agent"]
    MP("Main Planner Agent<br/>호출 순서 · 설명 조율")
  end
  PV --> MP

  subgraph G4["④ 코호트 인분수 계산"]
    AD["build_serving_input<br/>계약 → 계산기 어댑터"]
    SCI[["ServingCalculationInputV1<br/>계산기 전용 코호트"]]
    CS["calculate_serving_requirement<br/>결정적 코호트 계산"]
    SR[["ServingRequirementV1<br/>기본량 · 전략별 목표량"]]
    AD --> SCI --> CS --> SR
  end
  MP -->|인분수 요청| AD

  subgraph G5["⑤ 식당 · 메뉴 데이터"]
    SEARCH["search_menu_candidates<br/>근처 식당 · 메뉴 조회"]
    CSET[["CandidateMenuSet<br/>출처 있는 원시 후보"]]
    ENR("enrich_menu_semantics<br/>메뉴 의미 정규화")
    MSET[["NormalizedMenuSet<br/>정규화 · provenance"]]
    HE["apply_hard_eligibility<br/>알레르기 · 식단 필터"]
    ESET[["EligibleMenuSet<br/>hard constraint 통과"]]
    SEARCH --> CSET --> ENR --> MSET --> HE --> ESET
  end
  MP -->|메뉴 후보 요청| SEARCH

  subgraph G6["⑥ 조합 생성 · 선호 평가 · 검증"]
    GC["generate_budget_combinations<br/>정수 수량 · 예산 탐색"]
    COMB[["CombinationSet<br/>예산 내 유효 조합"]]
    SP("score_soft_preferences<br/>싫어하는 음식 · 선호 의미 평가")
    SSET[["ScoredCombinationSet<br/>soft score · 이유 코드"]]
    RV["rank_and_validate_plans<br/>최종 안전 · 예산 재검증"]
    PLAN[["Plan IDs<br/>추천 1 · 대안 2"]]
    GP["get_plan_for_presentation<br/>표시용 데이터 조회"]
    DISPLAY[["DisplayPlanV1<br/>사용자 표시 JSON"]]
    GC --> COMB --> SP --> SSET --> RV --> PLAN --> GP --> DISPLAY
  end

  SR -->|목표 인분수| GC
  ESET -->|eligible 메뉴| GC
  DISPLAY -->|표시 데이터| MP
  MP --> OUT(["최종 주문 계획<br/>수량 · 근거 · 대안"])

  subgraph G7["⑦ 서버 측 저장소 · 정책"]
    RSC[("Restaurant Snapshot Cache<br/>메뉴 · 가격 · freshness")]
    ES[("Evidence Store<br/>원문 · source span")]
    PR[("Policy Registry<br/>계수 · 매핑 · 한도")]
  end

  IA -.->|근거 저장| ES
  RSC -.->|snapshot| SEARCH
  ENR -.->|enrichment cache| RSC
  PR -.->|validation policy| DV
  PR -.->|alias mapping| AD
  PR -.->|factor policy| CS
  PR -.->|hard rules| HE
  PR -.->|search bounds| GC
  PR -.->|ranking policy| RV

  classDef ai fill:#34265f,stroke:#a78bfa,color:#f5f3ff,stroke-width:1.6px
  classDef deterministic fill:#102f52,stroke:#38bdf8,color:#e0f2fe,stroke-width:1.6px
  classDef artifact fill:#123a32,stroke:#34d399,color:#ecfdf5,stroke-width:1.6px
  classDef store fill:#293244,stroke:#94a3b8,color:#f1f5f9,stroke-width:1.6px
  classDef terminal fill:#4a2b18,stroke:#fb923c,color:#fff7ed,stroke-width:1.6px

  class IA,MP,ENR,SP ai
  class TR,PF,DV,AD,CS,SEARCH,HE,GC,RV,GP deterministic
  class CAND,INTAKE,PV,SCI,SR,CSET,MSET,ESET,COMB,SSET,PLAN,DISPLAY artifact
  class PCS,RSC,ES,PR store
  class U,CR,RJ,OUT terminal
```

## Trust and Computation Boundaries

| Category | Components | Rule |
| --- | --- | --- |
| AI agents | Interpreter, Main Planner, menu enrichment, soft-preference scoring | Interpret variable language, orchestrate, or explain; emit schema-validated structured output. |
| Deterministic functions | Preflight, profile validator, serving adapter/calculator, search adapter, hard eligibility, combination search, final validation | Own ranges, arithmetic, hard constraints, policy, bounds, and reproducibility. |
| Data artifacts | Candidate, intake, calculator input/output, menu sets, combination sets, plan IDs, display plan | Immutable/versioned stage boundaries; large artifacts remain server-side. |
| Stores | Planning Case Store, Restaurant Snapshot Cache, Evidence Store, Policy Registry | Not injected wholesale into prompts; tools retrieve only what a stage needs. |
| Terminal outcomes | Clarification, rejection, final plan | Controlled user-visible outcomes; no forced plan for invalid or impossible input. |

## Tool Arguments and Artifact IDs

| Tool or agent-as-tool | Inputs | Why anything beyond `case_id` is passed |
| --- | --- | --- |
| `build_serving_input` | `case_id` | The current case revision uniquely selects the validated profile and policy. |
| `calculate_serving_requirement` | `case_id` or `serving_calculation_input_id` | Pass the artifact ID when adapter outputs are versioned, compared, or retried. |
| `search_menu_candidates` | `case_id` | Location, categories, budget context, and snapshot policy resolve from the case. |
| `enrich_menu_semantics` | `case_id`, `candidate_set_id` | A case may have several searches/refreshes; the ID prevents enriching the wrong set. |
| `apply_hard_eligibility` | `case_id`, `menu_set_id` | It combines case-specific restrictions with one exact normalized menu version. |
| `generate_budget_combinations` | `case_id`, `eligible_set_id`, `serving_requirement_id` | It must join an exact eligible-menu branch with an exact demand calculation. |
| `score_soft_preferences` | `case_id`, `combination_set_id` | It scores one bounded candidate set against the case's semantic preferences. |
| `rank_and_validate_plans` | `case_id`, `scored_set_id` | Final checks must run on the exact scored version and current case revision. |
| `get_plan_for_presentation` | `case_id`, `plan_ids` | Only selected plans cross into the explanation prompt; the full search space stays server-side. |

Tools sharing `case_id` all need the current immutable user profile, policy version, and trace context. Tools receiving an additional artifact ID are consumers of a branchable/versioned intermediate result. This keeps tool prompts small and prevents accidental mixing of stale calculation and menu branches.

## Serving Adapter Boundary

`build_serving_input` is the compatibility seam between `PlanningJobV2` and the teammate's existing cohort calculator.

It must:

- Map contract appetite vocabulary to the existing calculator keys.
- Map `late_night` to `late_night_snack` and `minimize_shortage` to `avoid_shortage`.
- Expand only mutually exclusive validated cohorts, never one object per person unless needed.
- Preserve counts and exact explicit custom serving values.
- Apply calculator adjustment codes only when unambiguously supported.
- Detect mutually exclusive adjustments and flag potential double counting.
- Produce a calculator-only `ServingCalculationInputV1`; do not mutate `PlanningIntakeV2`.
- Record adapter version, serving policy ID, applied aliases, skipped adjustments, warnings, and assumptions.

The deterministic formula remains:

`cohort demand = cohort count × appetite factor × meal factor × accepted adjustment factors`

`group base demand = sum(cohort demand)`

`strategy target = capped group base demand × configured margin`

Use `Decimal` throughout calculation and convert to milli-servings at the defined output boundary. Never use binary floating point for business arithmetic.

## Replanning

Replan from the earliest affected artifact:

| Change | Earliest stage to rerun |
| --- | --- |
| Participant count, appetite, activity, recent meal, meal type | Profile validation, then serving adapter/calculation and all downstream stages. |
| Allergy, diet, strong exclusion | Profile validation, hard eligibility, combinations, scoring, and final validation. |
| Budget or shortage/leftover objective | Combination generation and downstream stages; serving strategy target may also change. |
| Restaurant/menu availability or serving evidence | Search/normalized menu set, eligibility, combinations, and downstream stages. |
| Soft dislike/preference only | Soft-preference scoring and downstream stages if the eligible/menu sets are unchanged. |
| Presentation wording only | Presentation retrieval/explanation only. |

Every artifact is tied to `case_id`, `profile_revision`, policy IDs, and upstream artifact IDs so stale branches can be rejected deterministically.

## Diagram Maintenance

To change the public diagram:

1. Edit `workflow-site/public/data/workflow.json`.
2. Keep node IDs stable when semantics do not change.
3. Validate that every group node ID and edge endpoint exists.
4. Run the diagram site's tests and production build.
5. Redeploy the nested `workflow-site` project.

The renderer already supports hover, click-to-pin, keyboard focus, and dataset-driven descriptions. Do not restore reliance on Mermaid-generated SVG IDs; they are not a stable API.
