"""Tests for Intake Classifier Agent (Agent 6.1)."""
import asyncio
from labelforge.agents.intake_classifier import IntakeClassifierAgent, CONFIDENCE_HITL_THRESHOLD
from tests.stubs import LLMProvider


def test_classifies_with_high_confidence(llm_provider):
    agent = IntakeClassifierAgent(llm_provider=llm_provider)
    result = asyncio.run(agent.execute({"document_content": "PO #12345 from Acme Corp"}))
    assert result.success is True
    assert result.confidence >= 0.95
    assert result.data["doc_class"] == "PURCHASE_ORDER"
    assert result.needs_hitl is False


def test_hitl_triggered_when_confidence_below_threshold(llm_provider):
    """Verify HiTL is triggered when confidence < 0.70."""
    agent = IntakeClassifierAgent(llm_provider=llm_provider)
    # Monkey-patch _parse_classification to return low confidence
    agent._parse_classification = lambda content: {"doc_class": "UNKNOWN", "confidence": 0.50}
    result = asyncio.run(agent.execute({"document_content": "ambiguous doc"}))
    assert result.needs_hitl is True
    assert result.success is False
    assert result.confidence < CONFIDENCE_HITL_THRESHOLD
    assert result.hitl_reason == "Low classification confidence"


def test_cost_tracked_in_result(llm_provider_factory):
    expected_cost = 0.0042
    llm = llm_provider_factory(cost=expected_cost)
    agent = IntakeClassifierAgent(llm_provider=llm)
    result = asyncio.run(agent.execute({"document_content": "some content"}))
    assert result.cost == expected_cost


def test_agent_id_is_correct(llm_provider):
    agent = IntakeClassifierAgent(llm_provider=llm_provider)
    assert agent.agent_id == "agent-6.1-intake-classifier"
