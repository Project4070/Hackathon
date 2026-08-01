from __future__ import annotations

from types import SimpleNamespace

import pytest

from group_food_agent.semantic_agents import (
    MenuSemanticCandidateV1,
    MenuSemanticEnricher,
    build_menu_enrichment_agent_tool,
    build_menu_semantic_agent,
    build_preference_scoring_agent,
)


def test_focused_semantic_agents_are_sdk_agents_without_tools():
    menu_agent = build_menu_semantic_agent()
    preference_agent = build_preference_scoring_agent()

    assert menu_agent.__class__.__module__.startswith("agents")
    assert preference_agent.__class__.__module__.startswith("agents")
    assert menu_agent.tools == []
    assert preference_agent.tools == []
    assert menu_agent.output_type is MenuSemanticCandidateV1
    nested_tool = build_menu_enrichment_agent_tool()
    assert nested_tool.name == "menu_semantic_enrichment_agent"


@pytest.mark.asyncio
async def test_enricher_preserves_source_phrase_and_caches_by_hash():
    calls = 0

    async def fake_runner(agent, prompt, max_turns, run_config):
        nonlocal calls
        calls += 1
        assert run_config.trace_include_sensitive_data is False
        return SimpleNamespace(
            final_output=MenuSemanticCandidateV1(
                normalized_name="Vegetable Pizza",
                category_code="pizza",
                variant_codes=["vegetable"],
                vegetarian_status="explicit_yes",
                vegetarian_evidence_phrase="vegetarian",
                spice_level="none",
                serving_cue_phrase="8 slices",
                status="explicit",
                confidence="high",
                ambiguity_reasons=[],
            )
        )

    enricher = MenuSemanticEnricher(runner=fake_runner)
    text = "<b>Vegetable Pizza</b>, 8 slices, vegetarian"
    first, first_hit = await enricher.enrich("https://example.org/menu", text)
    second, second_hit = await enricher.enrich("https://example.org/menu", text)

    assert first == second
    assert first_hit is False
    assert second_hit is True
    assert calls == 1


@pytest.mark.asyncio
async def test_enricher_rejects_model_invented_source_evidence():
    async def fake_runner(agent, prompt, max_turns, run_config):
        return SimpleNamespace(
            final_output=MenuSemanticCandidateV1(
                normalized_name="Pizza",
                category_code="pizza",
                variant_codes=[],
                vegetarian_status="unknown",
                vegetarian_evidence_phrase=None,
                spice_level="unknown",
                serving_cue_phrase="serves 20",
                status="ambiguous",
                confidence="low",
                ambiguity_reasons=["missing serving evidence"],
            )
        )

    with pytest.raises(ValueError, match="exact substring"):
        await MenuSemanticEnricher(runner=fake_runner).enrich(
            "https://example.org/menu", "Pizza, size unknown"
        )
