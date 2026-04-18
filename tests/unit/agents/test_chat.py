"""Tests for labelforge.agents.chat — handler + tool-call protocol."""
from __future__ import annotations

import asyncio
from typing import Any, Dict, List, Sequence

import pytest

from labelforge.agents.chat import (
    AgentChatHandler,
    ChatContext,
    ChatMessage,
    GenericChatHandler,
    clear_registry,
    filter_patches,
    get_chat_handler,
    parse_tool_call,
    register_chat_handler,
    set_chat_provider,
)
from labelforge.core.llm import CompletionResult, LLMProvider


# ── parse_tool_call ─────────────────────────────────────────────────────────


class TestParseToolCall:
    def test_plain_text_no_tool_call(self):
        visible, tool = parse_tool_call("Hello operator, I need the UPC.")
        assert visible == "Hello operator, I need the UPC."
        assert tool == {}

    def test_fenced_json_at_end_is_stripped(self):
        raw = 'Updating country.\n\n```json\n{"patches": {"country_of_origin": "CN"}, "resolved": true}\n```'
        visible, tool = parse_tool_call(raw)
        assert visible == "Updating country."
        assert tool == {
            "patches": {"country_of_origin": "CN"},
            "resolved": True,
        }

    def test_fenced_json_without_json_label(self):
        raw = 'Sure.\n\n```\n{"resolved": false}\n```'
        visible, tool = parse_tool_call(raw)
        assert visible == "Sure."
        assert tool == {"resolved": False}

    def test_mid_response_code_fence_is_not_treated_as_tool_call(self):
        # Agents sometimes quote code mid-reply — we only treat a fenced
        # block AT THE END as the tool-call envelope.
        raw = "Here's an example:\n\n```\n{\"x\": 1}\n```\n\nDid that help?"
        visible, tool = parse_tool_call(raw)
        assert "Here's an example" in visible
        assert "Did that help" in visible
        assert tool == {}

    def test_malformed_json_falls_back_to_full_text(self):
        raw = 'Reply text.\n\n```json\n{bogus: not-json}\n```'
        visible, tool = parse_tool_call(raw)
        # We preserve the full raw output untouched when JSON parsing fails
        # rather than silently dropping it — operator can still see what
        # the agent tried to say.
        assert visible == raw.strip()
        assert tool == {}

    def test_non_object_json_falls_back(self):
        raw = 'Reply.\n\n```json\n[1, 2, 3]\n```'
        visible, tool = parse_tool_call(raw)
        assert tool == {}

    def test_empty_input(self):
        assert parse_tool_call("") == ("", {})


# ── filter_patches ──────────────────────────────────────────────────────────


class TestFilterPatches:
    def test_empty_patches(self):
        assert filter_patches({}, ["foo"]) == ({}, [])

    def test_wildcard_allows_everything(self):
        applied, dropped = filter_patches(
            {"a": 1, "b.c": 2, "anything": 3}, ["*"],
        )
        assert applied == {"a": 1, "b.c": 2, "anything": 3}
        assert dropped == []

    def test_exact_match(self):
        applied, dropped = filter_patches(
            {"country_of_origin": "CN", "secret": "x"},
            ["country_of_origin"],
        )
        assert applied == {"country_of_origin": "CN"}
        assert dropped == ["secret"]

    def test_dotted_prefix_match(self):
        applied, dropped = filter_patches(
            {"fused.upc": "123", "fused.description": "Mug", "foo": "bar"},
            ["fused"],
        )
        assert applied == {"fused.upc": "123", "fused.description": "Mug"}
        assert dropped == ["foo"]

    def test_nonmatching_prefix_drops_everything(self):
        applied, dropped = filter_patches(
            {"foo": 1, "bar": 2}, ["unrelated"],
        )
        assert applied == {}
        assert set(dropped) == {"foo", "bar"}


# ── Registry ────────────────────────────────────────────────────────────────


class TestRegistry:
    def setup_method(self):
        clear_registry()

    def test_register_and_lookup(self):
        h = GenericChatHandler(
            agent_id="test_agent", role_description="test", patch_allowlist=(),
        )
        register_chat_handler(h)
        assert get_chat_handler("test_agent") is h

    def test_unknown_agent_returns_none(self):
        assert get_chat_handler("not_registered") is None

    def test_register_requires_agent_id(self):
        h = GenericChatHandler(
            agent_id="", role_description="x", patch_allowlist=(),
        )
        with pytest.raises(ValueError):
            register_chat_handler(h)

    def test_register_rejects_sentinel(self):
        class BadHandler(AgentChatHandler):
            pass  # inherits agent_id = "unknown"

        with pytest.raises(ValueError):
            register_chat_handler(BadHandler())


# ── Stub provider ───────────────────────────────────────────────────────────


class StubChatProvider(LLMProvider):
    """Minimal LLMProvider that returns a canned response per test."""

    def __init__(self, response: str, cost: float = 0.0) -> None:
        self.response = response
        self.cost = cost
        self.calls: List[Dict[str, Any]] = []

    @property
    def name(self) -> str:
        return "stub-chat"

    async def complete(
        self,
        model: str,
        messages: Sequence[Dict[str, str]],
        max_tokens: int = 4096,
        temperature: float = 0.0,
        **kwargs: Any,
    ) -> CompletionResult:
        self.calls.append({"model": model, "messages": list(messages)})
        return CompletionResult(
            content=self.response,
            model=model,
            input_tokens=100,
            output_tokens=50,
            cost_usd=self.cost,
            latency_ms=12.3,
            provider=self.name,
        )


# ── AgentChatHandler.respond ───────────────────────────────────────────────


def _ctx(**overrides: Any) -> ChatContext:
    defaults = dict(
        thread_id="t1",
        tenant_id="tenant-1",
        order_id="ORD-1",
        item_no="1",
        agent_id="test_agent",
        pause_context={"reason": "missing country_of_origin"},
        item_data={"upc": "012345", "description": "Mug"},
        messages=[
            ChatMessage(role="agent", content="I need the country of origin."),
            ChatMessage(role="human", content="It's China."),
        ],
    )
    defaults.update(overrides)
    return ChatContext(**defaults)


class TestHandlerRespond:
    def test_plain_text_reply(self):
        provider = StubChatProvider("Got it, thanks.")
        h = GenericChatHandler(
            agent_id="x", role_description="test agent",
            patch_allowlist=(), provider=provider,
        )
        reply = asyncio.run(h.respond(_ctx()))
        assert reply.text == "Got it, thanks."
        assert reply.patches == {}
        assert reply.resolved is False
        assert reply.cost_usd == 0.0

    def test_tool_call_applies_patches_and_signals_resolved(self):
        provider = StubChatProvider(
            'Setting country to China.\n\n```json\n'
            '{"patches": {"country_of_origin": "CN"}, "resolved": true}\n```'
        )
        h = GenericChatHandler(
            agent_id="x", role_description="fusion",
            patch_allowlist=("country_of_origin",),
            provider=provider,
        )
        reply = asyncio.run(h.respond(_ctx()))
        assert reply.text == "Setting country to China."
        assert reply.patches == {"country_of_origin": "CN"}
        assert reply.resolved is True

    def test_disallowed_patch_is_dropped_with_explainer(self):
        provider = StubChatProvider(
            'Updating.\n\n```json\n'
            '{"patches": {"country_of_origin": "CN", "admin_password": "x"}}\n```'
        )
        h = GenericChatHandler(
            agent_id="x", role_description="fusion",
            patch_allowlist=("country_of_origin",),
            provider=provider,
        )
        reply = asyncio.run(h.respond(_ctx()))
        # Allowed patch is applied
        assert reply.patches == {"country_of_origin": "CN"}
        # Operator is told about the rejected field
        assert "admin_password" in reply.text
        assert "not authorized" in reply.text.lower()

    def test_system_prompt_includes_pause_context_and_allowlist(self):
        provider = StubChatProvider("ok")
        h = GenericChatHandler(
            agent_id="fusion", role_description="the Fusion Agent",
            patch_allowlist=("upc", "country_of_origin"),
            provider=provider,
        )
        asyncio.run(h.respond(_ctx()))
        sys_msg = provider.calls[0]["messages"][0]
        assert sys_msg["role"] == "system"
        assert "fusion" in sys_msg["content"].lower()
        assert "upc" in sys_msg["content"]
        assert "country_of_origin" in sys_msg["content"]
        # Pause context verbatim
        assert "missing country_of_origin" in sys_msg["content"]

    def test_redaction_of_heavy_fields_in_prompt(self):
        # The item_data contains a fat SVG — we should NOT stuff that
        # into the prompt.
        provider = StubChatProvider("ok")
        h = GenericChatHandler(
            agent_id="x", role_description="t", patch_allowlist=(),
            provider=provider,
        )
        heavy_ctx = _ctx(item_data={
            "upc": "012345",
            "die_cut_svg": "<svg>" + ("x" * 50_000) + "</svg>",
        })
        asyncio.run(h.respond(heavy_ctx))
        sys_msg = provider.calls[0]["messages"][0]["content"]
        assert "<redacted" in sys_msg
        assert "xxx" * 100 not in sys_msg  # no raw SVG body

    def test_history_roles_mapped_for_openai(self):
        provider = StubChatProvider("ok")
        h = GenericChatHandler(
            agent_id="x", role_description="t", patch_allowlist=(),
            provider=provider,
        )
        asyncio.run(h.respond(_ctx()))
        msgs = provider.calls[0]["messages"]
        # system + agent("assistant") + human("user")
        assert [m["role"] for m in msgs] == ["system", "assistant", "user"]

    def test_provider_failure_returns_graceful_apology(self):
        class BoomProvider(StubChatProvider):
            async def complete(self, *a, **kw):
                raise RuntimeError("openai down")

        h = GenericChatHandler(
            agent_id="x", role_description="t", patch_allowlist=(),
            provider=BoomProvider("unused"),
        )
        reply = asyncio.run(h.respond(_ctx()))
        assert "sorry" in reply.text.lower()
        assert reply.resolved is False
        assert reply.patches == {}


# ── Tool-use + static context (DieCut HiTL access plan) ────────────────────


class TestToolCallParsing:
    def test_tools_array_surfaces_via_handler(self):
        provider = StubChatProvider(
            'Looking up the protocol.\n\n```json\n'
            '{"tools": [{"name": "get_document_text", '
            '"args": {"document_id": "idoc-1"}}]}\n```'
        )
        h = GenericChatHandler(
            agent_id="x", role_description="test agent",
            patch_allowlist=(), provider=provider,
        )
        reply = asyncio.run(h.respond(_ctx()))
        assert reply.has_tool_calls
        assert reply.tool_calls == [
            {"name": "get_document_text", "args": {"document_id": "idoc-1"}}
        ]
        assert reply.patches == {}
        assert reply.resolved is False

    def test_malformed_tools_entry_is_dropped(self):
        provider = StubChatProvider(
            '...\n\n```json\n'
            '{"tools": ["not-an-object", {"name": 42}, '
            '{"name": "list_compliance_rules"}]}\n```'
        )
        h = GenericChatHandler(
            agent_id="x", role_description="t", provider=provider,
        )
        reply = asyncio.run(h.respond(_ctx()))
        # Only the well-formed entry with a str name survives.
        assert reply.tool_calls == [
            {"name": "list_compliance_rules", "args": {}}
        ]


class TestSystemPromptStaticContext:
    def test_prompt_lists_tools_and_docs(self):
        provider = StubChatProvider("ok")
        h = GenericChatHandler(
            agent_id="compliance_eval_activity",
            role_description="the Compliance Classifier",
            patch_allowlist=("applicable_warnings",),
            provider=provider,
        )
        ctx = _ctx(
            importer_profile={
                "brand_treatment": {"company_name": "Acme Ltd"},
                "panel_layouts": {"front": [], "back": []},
                "handling_symbol_rules": {"fragile": True},
            },
            rules_summary=[{"rule_code": "SBH_CA_ALL_DOCS", "title": "CA gating", "region": "US"}],
            warnings_summary=[{"code": "US_NONFOOD_CERAMIC_HARMFUL", "title": "Non-food", "region": "US"}],
            documents_summary=[{"id": "idoc-af5d0e3a", "doc_type": "protocol", "filename": "carton-marking.pdf"}],
            onboarding_summary={"status": "ready_for_review", "agents": {"protocol": "completed"}, "extracted_keys": ["warnings", "checklist"]},
            sibling_items=[{"item_no": "2", "state": "FUSED"}],
        )
        asyncio.run(h.respond(ctx))
        sys_msg = provider.calls[0]["messages"][0]["content"]

        # Static summary bullets are present and machine-parseable.
        assert "Importer profile" in sys_msg
        assert "Acme Ltd" in sys_msg
        assert "Active compliance rules (1)" in sys_msg
        assert "SBH_CA_ALL_DOCS" in sys_msg
        assert "Warning labels (1)" in sys_msg
        assert "US_NONFOOD_CERAMIC_HARMFUL" in sys_msg
        assert "carton-marking.pdf" in sys_msg
        assert "Onboarding session" in sys_msg

        # Tool catalog is advertised.
        for tool_name in (
            "get_importer_profile",
            "list_compliance_rules",
            "list_warning_labels",
            "list_importer_documents",
            "get_document_text",
            "search_documents",
            "get_onboarding_extraction",
            "get_item_data",
        ):
            assert tool_name in sys_msg, f"tool {tool_name} missing from prompt"

        # Protocol explains the new "tools" key in the fenced block.
        assert '"tools"' in sys_msg
