"""Tests for Intake Classifier Agent (Agent 6.1)."""
import asyncio
import json

import pytest

from labelforge.agents.intake_classifier import (
    IntakeClassifierAgent,
    CONFIDENCE_HITL_THRESHOLD,
    VALID_CLASSES,
)


def test_classifies_with_high_confidence(llm_provider):
    """Agent returns high-confidence classification from valid LLM JSON."""
    llm_provider._default_content = json.dumps({
        "doc_class": "PURCHASE_ORDER",
        "confidence": 0.97,
        "reasoning": "Contains PO number and line items",
    })
    agent = IntakeClassifierAgent(llm_provider=llm_provider)
    result = asyncio.run(agent.execute({
        "document_content": "PO #12345 from Acme Corp",
        "filename": "PO-12345.pdf",
    }))
    assert result.success is True
    assert result.confidence >= 0.95
    assert result.data["doc_class"] == "PURCHASE_ORDER"
    assert result.needs_hitl is False


def test_hitl_triggered_when_confidence_below_threshold(llm_provider):
    """Verify HiTL is triggered when confidence < 0.70."""
    llm_provider._default_content = json.dumps({
        "doc_class": "UNKNOWN",
        "confidence": 0.50,
        "reasoning": "Ambiguous document",
    })
    agent = IntakeClassifierAgent(llm_provider=llm_provider)
    result = asyncio.run(agent.execute({
        "document_content": "ambiguous doc",
        "filename": "mystery.pdf",
    }))
    assert result.needs_hitl is True
    assert result.success is False
    assert result.confidence < CONFIDENCE_HITL_THRESHOLD
    assert result.hitl_reason == "Low classification confidence"


def test_cost_tracked_in_result(llm_provider_factory):
    expected_cost = 0.0042
    llm = llm_provider_factory(
        default_content=json.dumps({"doc_class": "PURCHASE_ORDER", "confidence": 0.95}),
        cost=expected_cost,
    )
    agent = IntakeClassifierAgent(llm_provider=llm)
    result = asyncio.run(agent.execute({
        "document_content": "some content",
        "filename": "test.pdf",
    }))
    assert result.cost == expected_cost


def test_agent_id_is_correct(llm_provider):
    agent = IntakeClassifierAgent(llm_provider=llm_provider)
    assert agent.agent_id == "agent-6.1-intake-classifier"


def test_fallback_to_filename_on_invalid_json(llm_provider):
    """When LLM returns non-JSON, fallback to filename-based classification."""
    llm_provider._default_content = "I think this is a purchase order"
    agent = IntakeClassifierAgent(llm_provider=llm_provider)
    result = asyncio.run(agent.execute({
        "document_content": "some content",
        "filename": "PO-88210.pdf",
    }))
    assert result.data["doc_class"] == "PURCHASE_ORDER"
    assert result.data["confidence"] == 0.60


def test_fallback_unknown_filename(llm_provider):
    """When LLM returns bad JSON and filename is unrecognizable."""
    llm_provider._default_content = "not json"
    agent = IntakeClassifierAgent(llm_provider=llm_provider)
    result = asyncio.run(agent.execute({
        "document_content": "some content",
        "filename": "document-12345.xyz",
    }))
    assert result.data["doc_class"] == "UNKNOWN"
    assert result.data["confidence"] == 0.0
    assert result.needs_hitl is True


def test_classify_proforma_invoice(llm_provider):
    llm_provider._default_content = json.dumps({
        "doc_class": "PROFORMA_INVOICE",
        "confidence": 0.93,
        "reasoning": "Contains dimensions and carton counts",
    })
    agent = IntakeClassifierAgent(llm_provider=llm_provider)
    result = asyncio.run(agent.execute({
        "document_content": "PI content",
        "filename": "PI-88210.xlsx",
    }))
    assert result.data["doc_class"] == "PROFORMA_INVOICE"
    assert result.confidence >= 0.90


def test_classify_warning_labels(llm_provider):
    llm_provider._default_content = json.dumps({
        "doc_class": "WARNING_LABELS",
        "confidence": 0.88,
    })
    agent = IntakeClassifierAgent(llm_provider=llm_provider)
    result = asyncio.run(agent.execute({
        "document_content": "Prop 65 Warning",
        "filename": "warnings.pdf",
    }))
    assert result.data["doc_class"] == "WARNING_LABELS"


def test_invalid_doc_class_clamped_to_unknown(llm_provider):
    """If LLM returns an invalid doc_class, it should be set to UNKNOWN."""
    llm_provider._default_content = json.dumps({
        "doc_class": "NONEXISTENT_TYPE",
        "confidence": 0.95,
    })
    agent = IntakeClassifierAgent(llm_provider=llm_provider)
    result = asyncio.run(agent.execute({
        "document_content": "content",
        "filename": "test.pdf",
    }))
    assert result.data["doc_class"] == "UNKNOWN"
    assert result.data["confidence"] <= 0.3


def test_confidence_clamped_to_0_1(llm_provider):
    """Confidence outside [0, 1] should be clamped."""
    llm_provider._default_content = json.dumps({
        "doc_class": "PURCHASE_ORDER",
        "confidence": 1.5,
    })
    agent = IntakeClassifierAgent(llm_provider=llm_provider)
    result = asyncio.run(agent.execute({
        "document_content": "content",
        "filename": "test.pdf",
    }))
    assert result.confidence == 1.0


def test_valid_classes_matches_document_class_enum():
    from labelforge.contracts.models import DocumentClass
    expected = {dc.value for dc in DocumentClass if dc != DocumentClass.UNKNOWN}
    assert VALID_CLASSES == expected


def test_messages_sent_to_llm(llm_provider):
    """Verify the agent sends system + user messages to the LLM."""
    llm_provider._default_content = json.dumps({
        "doc_class": "PURCHASE_ORDER",
        "confidence": 0.95,
    })
    agent = IntakeClassifierAgent(llm_provider=llm_provider)
    asyncio.run(agent.execute({
        "document_content": "PO content here",
        "filename": "my-po.pdf",
    }))
    assert len(llm_provider.calls) == 1
    call = llm_provider.calls[0]
    assert call["messages"] is not None
    assert len(call["messages"]) == 2
    assert call["messages"][0]["role"] == "system"
    assert call["messages"][1]["role"] == "user"
    assert "my-po.pdf" in call["messages"][1]["content"]
