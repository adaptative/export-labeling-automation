"""Tests for Checklist Rule Extractor Agent (Agent 6.6)."""
import asyncio
from labelforge.agents.checklist_extractor import ChecklistExtractorAgent, CONFIDENCE_HITL_THRESHOLD


def test_extracts_rules(llm_provider):
    agent = ChecklistExtractorAgent(llm_provider=llm_provider)
    result = asyncio.run(agent.execute({
        "document_content": "1. Prop 65 warning required for wood products\n2. CPSIA lead test for children's items",
    }))
    assert result.success is True
    assert result.confidence >= CONFIDENCE_HITL_THRESHOLD
    rules = result.data["rules"]
    assert len(rules) >= 1
    assert "rule_code" in rules[0]
    assert "conditions" in rules[0]


def test_and_or_not_operators(llm_provider):
    agent = ChecklistExtractorAgent(llm_provider=llm_provider)
    result = asyncio.run(agent.execute({
        "document_content": "Prop 65 applies to wood AND plastic products sold in US",
    }))
    rules = result.data["rules"]
    # Check that the fallback rules contain AND operator
    has_and = any("AND" in str(r.get("conditions", {})) for r in rules)
    assert has_and is True


def test_hitl_triggered_below_threshold(llm_provider):
    agent = ChecklistExtractorAgent(llm_provider=llm_provider)
    agent._parse_response = lambda content: {"rules": [{"rule_code": "X"}], "confidence": 0.70}
    result = asyncio.run(agent.execute({"document_content": "ambiguous checklist"}))
    assert result.needs_hitl is True
    assert result.confidence < CONFIDENCE_HITL_THRESHOLD


def test_validates_missing_rule_code(llm_provider):
    agent = ChecklistExtractorAgent(llm_provider=llm_provider)
    agent._parse_response = lambda content: {"rules": [{"title": "No code"}], "confidence": 0.95}
    result = asyncio.run(agent.execute({"document_content": "checklist"}))
    assert result.needs_hitl is True
    assert "missing rule_code" in result.hitl_reason


def test_cost_tracked(llm_provider_factory):
    llm = llm_provider_factory(cost=0.004)
    agent = ChecklistExtractorAgent(llm_provider=llm)
    result = asyncio.run(agent.execute({"document_content": "content"}))
    assert result.cost == 0.004


def test_agent_id(llm_provider):
    agent = ChecklistExtractorAgent(llm_provider=llm_provider)
    assert agent.agent_id == "agent-6.6-checklist-extractor"
