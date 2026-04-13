"""Tests for Protocol Analyzer Agent (Agent 6.4)."""
import asyncio
from labelforge.agents.protocol_analyzer import ProtocolAnalyzerAgent, CONFIDENCE_HITL_THRESHOLD


def test_extracts_all_sections(llm_provider):
    agent = ProtocolAnalyzerAgent(llm_provider=llm_provider)
    result = asyncio.run(agent.execute({
        "document_content": "Brand: Blue #003DA5, Logo top-right, fragile, this-side-up",
        "importer_id": "IMP-ACME",
    }))
    assert result.success is True
    assert result.confidence >= CONFIDENCE_HITL_THRESHOLD
    assert "brand_treatment" in result.data
    assert "panel_layouts" in result.data
    assert "handling_symbol_rules" in result.data
    assert result.data["importer_id"] == "IMP-ACME"


def test_hitl_triggered_below_threshold(llm_provider):
    agent = ProtocolAnalyzerAgent(llm_provider=llm_provider)
    agent._parse_response = lambda content: {"confidence": 0.50, "brand_treatment": {}}
    result = asyncio.run(agent.execute({
        "document_content": "ambiguous",
        "importer_id": "IMP-TEST",
    }))
    assert result.needs_hitl is True
    assert result.confidence < CONFIDENCE_HITL_THRESHOLD
    assert "Missing sections" in result.hitl_reason


def test_cost_tracked(llm_provider_factory):
    llm = llm_provider_factory(cost=0.005)
    agent = ProtocolAnalyzerAgent(llm_provider=llm)
    result = asyncio.run(agent.execute({
        "document_content": "some content",
        "importer_id": "IMP-TEST",
    }))
    assert result.cost == 0.005


def test_agent_id(llm_provider):
    agent = ProtocolAnalyzerAgent(llm_provider=llm_provider)
    assert agent.agent_id == "agent-6.4-protocol-analyzer"


def test_images_mentioned_in_prompt(llm_provider):
    agent = ProtocolAnalyzerAgent(llm_provider=llm_provider)
    asyncio.run(agent.execute({
        "document_content": "protocol content",
        "importer_id": "IMP-ACME",
        "images": ["base64img1", "base64img2"],
    }))
    assert "2 annotated photo" in llm_provider.calls[0]["prompt"]
