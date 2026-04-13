"""Tests for Warning Label Parser Agent (Agent 6.5)."""
import asyncio
from labelforge.agents.warning_label_parser import WarningLabelParserAgent, CONFIDENCE_HITL_THRESHOLD


def test_extracts_labels(llm_provider):
    agent = WarningLabelParserAgent(llm_provider=llm_provider)
    result = asyncio.run(agent.execute({
        "document_content": "Prop 65 warning: cancer risk chemicals...",
    }))
    assert result.success is True
    assert result.confidence >= CONFIDENCE_HITL_THRESHOLD
    labels = result.data["labels"]
    assert len(labels) >= 1
    assert "text_en" in labels[0]
    assert "placement_rules" in labels[0]


def test_hitl_triggered_below_threshold(llm_provider):
    agent = WarningLabelParserAgent(llm_provider=llm_provider)
    agent._parse_response = lambda content: {"labels": [{"label_code": "X"}], "confidence": 0.80}
    result = asyncio.run(agent.execute({
        "document_content": "unclear label text",
    }))
    assert result.needs_hitl is True
    assert result.confidence < CONFIDENCE_HITL_THRESHOLD
    assert "legal threshold" in result.hitl_reason


def test_region_passed_through(llm_provider):
    agent = WarningLabelParserAgent(llm_provider=llm_provider)
    result = asyncio.run(agent.execute({
        "document_content": "EU warning labels",
        "region": "EU",
    }))
    assert result.data["region"] == "EU"


def test_cost_tracked(llm_provider_factory):
    llm = llm_provider_factory(cost=0.007)
    agent = WarningLabelParserAgent(llm_provider=llm)
    result = asyncio.run(agent.execute({"document_content": "content"}))
    assert result.cost == 0.007


def test_agent_id(llm_provider):
    agent = WarningLabelParserAgent(llm_provider=llm_provider)
    assert agent.agent_id == "agent-6.5-warning-label-parser"


def test_high_confidence_threshold():
    assert CONFIDENCE_HITL_THRESHOLD == 0.95
