"""Tests for the fusion pipeline — _run_fusion, fuse endpoint, workflow activities."""
from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from labelforge.agents.base import AgentResult


# ── _run_fusion background task ───────────────────────────────────────────


class TestRunFusion:
    @pytest.mark.asyncio
    async def test_fusion_merges_po_and_pi_items(self):
        """Fusion should merge PO and PI items and update state to FUSED."""
        mock_po_item = MagicMock()
        mock_po_item.item_no = "001"
        mock_po_item.data = {"item_no": "001", "upc": "012345678905", "description": "Widget"}

        mock_pi_item = MagicMock()
        mock_pi_item.item_no = "001"
        mock_pi_item.data = {"item_no": "001", "box_L": 10.0, "box_W": 8.0, "box_H": 6.0, "total_cartons": 20}

        fusion_result = AgentResult(
            success=True,
            data={
                "fused_items": [
                    {"item_no": "001", "upc": "012345678905", "description": "Widget",
                     "box_L": 10.0, "box_W": 8.0, "box_H": 6.0, "total_cartons": 20},
                ],
                "issues": [],
            },
            confidence=0.95,
        )

        with patch("labelforge.agents.fusion.FusionAgent") as MockFusion, \
             patch("labelforge.db.session.async_session_factory") as mock_factory:

            mock_agent = AsyncMock()
            mock_agent.execute.return_value = fusion_result
            MockFusion.return_value = mock_agent

            # First call: get all items; Second call: get item by item_no
            mock_db = AsyncMock()
            mock_scalars_all = MagicMock()
            mock_scalars_all.scalars.return_value.all.return_value = [mock_po_item, mock_pi_item]

            mock_fused_item_db = MagicMock()
            mock_scalar_one = MagicMock()
            mock_scalar_one.scalar_one_or_none.return_value = mock_fused_item_db

            mock_db.execute = AsyncMock(side_effect=[mock_scalars_all, mock_scalar_one])
            mock_factory.return_value.__aenter__ = AsyncMock(return_value=mock_db)
            mock_factory.return_value.__aexit__ = AsyncMock(return_value=False)

            import importlib
            import labelforge.api.v1.orders as orders_mod
            importlib.reload(orders_mod)

            await orders_mod._run_fusion(order_id="ORD-001", tenant_id="tnt-001")

            # Verify FusionAgent was called with correct items
            mock_agent.execute.assert_called_once()
            call_data = mock_agent.execute.call_args[0][0]
            assert len(call_data["po_items"]) == 1
            assert len(call_data["pi_items"]) == 1

    @pytest.mark.asyncio
    async def test_fusion_no_items_returns_early(self):
        """If order has no items, fusion should return without calling agent."""
        with patch("labelforge.db.session.async_session_factory") as mock_factory:
            mock_db = AsyncMock()
            mock_result = MagicMock()
            mock_result.scalars.return_value.all.return_value = []
            mock_db.execute.return_value = mock_result
            mock_factory.return_value.__aenter__ = AsyncMock(return_value=mock_db)
            mock_factory.return_value.__aexit__ = AsyncMock(return_value=False)

            import importlib
            import labelforge.api.v1.orders as orders_mod
            importlib.reload(orders_mod)

            # Should not raise
            await orders_mod._run_fusion(order_id="ORD-001", tenant_id="tnt-001")

    @pytest.mark.asyncio
    async def test_fusion_error_does_not_raise(self):
        """Fusion errors should be caught and logged, not re-raised."""
        with patch("labelforge.db.session.async_session_factory") as mock_factory:
            mock_db = AsyncMock()
            mock_db.execute.side_effect = RuntimeError("DB unavailable")
            mock_factory.return_value.__aenter__ = AsyncMock(return_value=mock_db)
            mock_factory.return_value.__aexit__ = AsyncMock(return_value=False)

            import importlib
            import labelforge.api.v1.orders as orders_mod
            importlib.reload(orders_mod)

            # Should not raise
            await orders_mod._run_fusion(order_id="ORD-001", tenant_id="tnt-001")


# ── POST /orders/{id}/fuse endpoint ──────────────────────────────────────


class TestFuseEndpoint:
    def test_fuse_valid_order(self, client, admin_headers):
        """Fuse endpoint should accept valid orders with items."""
        resp = client.post("/api/v1/orders/ORD-2026-0042/fuse", headers=admin_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert data["order_id"] == "ORD-2026-0042"
        assert "item_count" in data
        assert "message" in data

    def test_fuse_nonexistent_order(self, client, admin_headers):
        resp = client.post("/api/v1/orders/ORD-NONEXISTENT/fuse", headers=admin_headers)
        assert resp.status_code == 404

    def test_fuse_requires_auth(self, client):
        resp = client.post("/api/v1/orders/ORD-2026-0042/fuse")
        assert resp.status_code == 401


# ── Workflow activity: parse_document_activity ────────────────────────────


class TestParseDocumentActivity:
    @pytest.mark.asyncio
    async def test_parse_po_document(self):
        """parse_document_activity should call POParserAgent for PO docs."""
        from labelforge.workflows.order_processor import parse_document_activity, ActivityInput

        mock_result = AgentResult(
            success=True,
            data={
                "items": [{"item_no": "001", "description": "Widget"}],
                "issues": [],
                "page_count": 1,
            },
            confidence=0.9,
            cost=0.01,
        )

        with patch("labelforge.agents.po_parser.POParserAgent") as MockPO, \
             patch("labelforge.core.llm.OpenAIProvider"), \
             patch("labelforge.config.settings") as mock_settings:

            mock_settings.openai_api_key = "test-key"
            mock_settings.llm_default_model = "gpt-4o"

            mock_agent = AsyncMock()
            mock_agent.execute.return_value = mock_result
            MockPO.return_value = mock_agent

            import importlib
            import labelforge.workflows.order_processor as wp
            importlib.reload(wp)

            input_data = wp.ActivityInput(
                order_id="ORD-001",
                item_id="itm-001",
                tenant_id="tnt-001",
                payload={"doc_class": "PURCHASE_ORDER", "document_content": "PO text here"},
            )
            output = await wp.parse_document_activity(input_data)

            assert output.success is True
            assert output.new_state == "PARSED"
            assert len(output.data["items"]) == 1
            mock_agent.execute.assert_called_once()

    @pytest.mark.asyncio
    async def test_parse_pi_document(self):
        """parse_document_activity should call PIParserAgent for PI docs."""
        from labelforge.workflows.order_processor import ActivityInput

        mock_result = AgentResult(
            success=True,
            data={
                "items": [{"item_no": "A1", "box_L": 10.0}],
                "warnings": [],
                "row_count": 1,
            },
            confidence=0.95,
            cost=0.0,
        )

        with patch("labelforge.agents.pi_parser.PIParserAgent") as MockPI:
            mock_agent = AsyncMock()
            mock_agent.execute.return_value = mock_result
            MockPI.return_value = mock_agent

            import importlib
            import labelforge.workflows.order_processor as wp
            importlib.reload(wp)

            input_data = wp.ActivityInput(
                order_id="ORD-001",
                item_id="itm-001",
                tenant_id="tnt-001",
                payload={
                    "doc_class": "PROFORMA_INVOICE",
                    "document_content": "item_no\tbox_l\nA1\t10",
                },
            )
            output = await wp.parse_document_activity(input_data)

            assert output.success is True
            assert output.new_state == "PARSED"
            mock_agent.execute.assert_called_once()

    @pytest.mark.asyncio
    async def test_parse_empty_content_passthrough(self):
        """Empty document content should pass through without calling agent."""
        import labelforge.workflows.order_processor as wp

        input_data = wp.ActivityInput(
            order_id="ORD-001",
            item_id="itm-001",
            tenant_id="tnt-001",
            payload={"doc_class": "PURCHASE_ORDER", "document_content": ""},
        )
        output = await wp.parse_document_activity(input_data)
        assert output.success is True
        assert output.new_state == "PARSED"

    @pytest.mark.asyncio
    async def test_parse_unknown_doc_class_passthrough(self):
        """Unknown doc class should pass through without calling agent."""
        import labelforge.workflows.order_processor as wp

        input_data = wp.ActivityInput(
            order_id="ORD-001",
            item_id="itm-001",
            tenant_id="tnt-001",
            payload={"doc_class": "CHECKLIST", "document_content": "some content"},
        )
        output = await wp.parse_document_activity(input_data)
        assert output.success is True
        assert output.new_state == "PARSED"


# ── Workflow activity: fuse_data_activity ─────────────────────────────────


class TestFuseDataActivity:
    @pytest.mark.asyncio
    async def test_fuse_data_calls_fusion_agent(self):
        """fuse_data_activity should call FusionAgent with PO+PI items."""
        fusion_result = AgentResult(
            success=True,
            data={
                "fused_items": [
                    {"item_no": "001", "upc": "012345678905", "box_L": 10.0},
                ],
                "issues": [],
            },
            confidence=0.95,
            cost=0.02,
        )

        with patch("labelforge.agents.fusion.FusionAgent") as MockFusion, \
             patch("labelforge.config.settings") as mock_settings:

            mock_settings.openai_api_key = ""  # No LLM — deterministic only

            mock_agent = AsyncMock()
            mock_agent.execute.return_value = fusion_result
            MockFusion.return_value = mock_agent

            import importlib
            import labelforge.workflows.order_processor as wp
            importlib.reload(wp)

            input_data = wp.ActivityInput(
                order_id="ORD-001",
                item_id="itm-001",
                tenant_id="tnt-001",
                payload={
                    "po_items": [{"item_no": "001", "upc": "012345678905"}],
                    "pi_items": [{"item_no": "001", "box_L": 10.0}],
                },
            )
            output = await wp.fuse_data_activity(input_data)

            assert output.success is True
            assert output.new_state == "FUSED"
            assert len(output.data["fused_items"]) == 1
            mock_agent.execute.assert_called_once()

    @pytest.mark.asyncio
    async def test_fuse_empty_items_passthrough(self):
        """No PO/PI items should pass through without calling agent."""
        import labelforge.workflows.order_processor as wp

        input_data = wp.ActivityInput(
            order_id="ORD-001",
            item_id="itm-001",
            tenant_id="tnt-001",
            payload={},
        )
        output = await wp.fuse_data_activity(input_data)
        assert output.success is True
        assert output.new_state == "FUSED"

    @pytest.mark.asyncio
    async def test_fuse_with_critical_issues_needs_hitl(self):
        """Critical fusion issues should set needs_hitl=True."""
        fusion_result = AgentResult(
            success=False,
            data={
                "fused_items": [],
                "issues": [{"item_no": "001", "severity": "critical", "message": "Missing from PI"}],
            },
            confidence=0.50,
            needs_hitl=True,
            hitl_reason="Critical fusion issues found",
            cost=0.01,
        )

        with patch("labelforge.agents.fusion.FusionAgent") as MockFusion, \
             patch("labelforge.config.settings") as mock_settings:

            mock_settings.openai_api_key = ""

            mock_agent = AsyncMock()
            mock_agent.execute.return_value = fusion_result
            MockFusion.return_value = mock_agent

            import importlib
            import labelforge.workflows.order_processor as wp
            importlib.reload(wp)

            input_data = wp.ActivityInput(
                order_id="ORD-001",
                item_id="itm-001",
                tenant_id="tnt-001",
                payload={
                    "po_items": [{"item_no": "001"}],
                    "pi_items": [],
                },
            )
            output = await wp.fuse_data_activity(input_data)

            assert output.success is False
            assert output.needs_hitl is True
            assert "Critical" in output.hitl_reason

    @pytest.mark.asyncio
    async def test_fuse_agent_error_returns_failed(self):
        """Agent exceptions should result in FAILED state."""
        with patch("labelforge.agents.fusion.FusionAgent") as MockFusion, \
             patch("labelforge.config.settings") as mock_settings:

            mock_settings.openai_api_key = ""

            mock_agent = AsyncMock()
            mock_agent.execute.side_effect = RuntimeError("Agent error")
            MockFusion.return_value = mock_agent

            import importlib
            import labelforge.workflows.order_processor as wp
            importlib.reload(wp)

            input_data = wp.ActivityInput(
                order_id="ORD-001",
                item_id="itm-001",
                tenant_id="tnt-001",
                payload={
                    "po_items": [{"item_no": "001"}],
                    "pi_items": [{"item_no": "001"}],
                },
            )
            output = await wp.fuse_data_activity(input_data)

            assert output.success is False
            assert output.new_state == "FAILED"


# ── _LLMProviderWrapper with FusionAgent ──────────────────────────────────


class TestLLMProviderWrapperWithFusion:
    @pytest.mark.asyncio
    async def test_wrapper_works_with_fusion_agent(self):
        """_LLMProviderWrapper should bridge correctly for FusionAgent."""
        from labelforge.agents.fusion import FusionAgent
        from labelforge.api.v1.orders import _LLMProviderWrapper

        mock_provider = AsyncMock()
        mock_provider.complete.return_value = MagicMock(
            content='{"material": "Ceramic", "finish": "Matte"}',
            cost_usd=0.005,
        )

        wrapper = _LLMProviderWrapper(mock_provider, "gpt-4o")
        agent = FusionAgent(llm_provider=wrapper)

        result = await agent.execute({
            "po_items": [{"item_no": "001", "description": "Ceramic Bowl", "upc": "012345678905"}],
            "pi_items": [{"item_no": "001", "box_L": 10.0, "box_W": 8.0, "box_H": 6.0, "total_cartons": 20}],
        })

        assert result.success is True
        fused = result.data["fused_items"]
        assert len(fused) == 1
        assert fused[0].get("material") == "Ceramic"
        assert fused[0].get("finish") == "Matte"

    @pytest.mark.asyncio
    async def test_wrapper_works_with_po_parser(self):
        """_LLMProviderWrapper should bridge correctly for POParserAgent."""
        import json
        from labelforge.agents.po_parser import POParserAgent
        from labelforge.api.v1.orders import _LLMProviderWrapper

        items_json = json.dumps([{
            "item_no": "001",
            "upc": "012345678905",
            "description": "Vase",
            "case_qty": "10",
            "total_qty": 200,
        }])

        mock_provider = AsyncMock()
        mock_provider.complete.return_value = MagicMock(
            content=items_json,
            cost_usd=0.01,
        )

        wrapper = _LLMProviderWrapper(mock_provider, "gpt-4o")
        agent = POParserAgent(llm_provider=wrapper)

        result = await agent.execute({"document_content": "PO with item 001"})

        assert len(result.data["items"]) == 1
        assert result.data["items"][0]["item_no"] == "001"


# ── Auto-fusion trigger after item extraction ─────────────────────────────


class TestAutoFusionTrigger:
    @pytest.mark.asyncio
    async def test_fusion_chains_when_both_po_and_pi_exist(self):
        """After item extraction, if both PO and PI items exist, fusion should auto-trigger."""
        from labelforge.agents.base import AgentResult

        mock_pi_result = AgentResult(
            success=True,
            data={"items": [
                {"item_no": "001", "box_L": 10.0, "box_W": 8.0, "box_H": 6.0, "total_cartons": 20},
            ]},
            confidence=0.95,
        )

        # Simulate: PI extraction creates items, and PO items already exist
        mock_po_item = MagicMock()
        mock_po_item.item_no = "001"
        mock_po_item.data = {"upc": "012345678905", "description": "Widget"}

        mock_pi_db_item = MagicMock()
        mock_pi_db_item.item_no = "001"
        mock_pi_db_item.data = {"box_L": 10.0, "total_cartons": 20}

        with patch("labelforge.agents.pi_parser.PIParserAgent") as MockPI, \
             patch("labelforge.db.session.async_session_factory") as mock_factory:

            mock_agent = AsyncMock()
            mock_agent.execute.return_value = mock_pi_result
            MockPI.return_value = mock_agent

            mock_db = AsyncMock()

            # First execute: check existing item_nos (dedup)
            mock_dedup_result = MagicMock()
            mock_dedup_result.all.return_value = []

            # Second execute: check all items for fusion trigger
            mock_all_items_result = MagicMock()
            mock_all_items_result.scalars.return_value.all.return_value = [mock_po_item, mock_pi_db_item]

            mock_db.execute = AsyncMock(side_effect=[mock_dedup_result, mock_all_items_result])
            mock_factory.return_value.__aenter__ = AsyncMock(return_value=mock_db)
            mock_factory.return_value.__aexit__ = AsyncMock(return_value=False)

            import importlib
            import labelforge.api.v1.orders as orders_mod
            importlib.reload(orders_mod)

            with patch.object(orders_mod, "_run_fusion") as mock_run_fusion:
                await orders_mod._run_item_extraction(
                    order_id="ORD-001",
                    tenant_id="tnt-001",
                    doc_class="PROFORMA_INVOICE",
                    doc_content="item_no\tbox_l\tbox_w\tbox_h\ttotal_cartons\n001\t10\t8\t6\t20",
                    filename="PI.txt",
                )

                mock_run_fusion.assert_called_once_with(
                    order_id="ORD-001",
                    tenant_id="tnt-001",
                )
