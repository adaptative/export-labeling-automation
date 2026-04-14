"""Tests for the AI classification + item extraction pipeline.

Covers:
  - _run_ai_classification background task
  - _run_item_extraction (PO and PI paths)
  - _LLMProviderWrapper adapter
  - _text_to_rows helper
  - _auto_detect_pi_mapping helper
  - Item deduplication logic
  - Classification status transitions
  - upload_order_document endpoint
  - Preview dual auth (header vs query param)
  - OrderItem.data field in responses
  - Integration: upload → classify → extract
"""
from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from labelforge.api.v1.orders import (
    _LLMProviderWrapper,
    _auto_detect_pi_mapping,
    _text_to_rows,
)


# ── _text_to_rows ──────────────────────────────────────────────────────────


class TestTextToRows:
    def test_tab_separated(self):
        content = "item_no\tqty\tprice\n001\t10\t5.99\n002\t20\t3.49"
        rows = _text_to_rows(content)
        assert len(rows) == 2
        assert rows[0]["item_no"] == "001"
        assert rows[0]["qty"] == "10"
        assert rows[1]["price"] == "3.49"

    def test_comma_separated(self):
        content = "item_no,qty,price\n001,10,5.99\n002,20,3.49"
        rows = _text_to_rows(content)
        assert len(rows) == 2
        assert rows[0]["item_no"] == "001"
        assert rows[1]["qty"] == "20"

    def test_empty_content(self):
        assert _text_to_rows("") == []

    def test_header_only(self):
        assert _text_to_rows("col1\tcol2") == []

    def test_blank_lines_skipped(self):
        content = "a\tb\n\n1\t2\n\n3\t4\n"
        rows = _text_to_rows(content)
        assert len(rows) == 2

    def test_empty_rows_skipped(self):
        content = "a\tb\n\t\n1\t2"
        rows = _text_to_rows(content)
        # Row with all empty values should be skipped
        assert len(rows) == 1
        assert rows[0]["a"] == "1"

    def test_missing_cells_filled_empty(self):
        content = "a\tb\tc\n1"
        rows = _text_to_rows(content)
        assert len(rows) == 1
        assert rows[0]["a"] == "1"
        assert rows[0]["b"] == ""
        assert rows[0]["c"] == ""

    def test_extra_cells_ignored(self):
        content = "a\tb\n1\t2\t3\t4"
        rows = _text_to_rows(content)
        assert len(rows) == 1
        assert rows[0]["a"] == "1"
        assert rows[0]["b"] == "2"

    def test_whitespace_stripped(self):
        content = " item_no \t qty \n 001 \t 10 "
        rows = _text_to_rows(content)
        assert rows[0]["item_no"] == "001"
        assert rows[0]["qty"] == "10"


# ── _auto_detect_pi_mapping ────────────────────────────────────────────────


class TestAutoDetectPiMapping:
    def test_exact_match(self):
        rows = [{"item_no": "1", "box_l": "10", "total_cartons": "5"}]
        mapping = _auto_detect_pi_mapping(rows)
        assert mapping["item_no"] == "item_no"
        assert mapping["box_L"] == "box_l"
        assert mapping["total_cartons"] == "total_cartons"

    def test_alternative_names(self):
        rows = [{"sku": "A1", "length": "10", "width": "5", "height": "3", "cartons": "20"}]
        mapping = _auto_detect_pi_mapping(rows)
        assert mapping["item_no"] == "sku"
        assert mapping["box_L"] == "length"
        assert mapping["box_W"] == "width"
        assert mapping["box_H"] == "height"
        assert mapping["total_cartons"] == "cartons"

    def test_empty_rows(self):
        assert _auto_detect_pi_mapping([]) == {}

    def test_no_matching_columns(self):
        rows = [{"foo": "1", "bar": "2"}]
        mapping = _auto_detect_pi_mapping(rows)
        assert mapping == {}

    def test_hs_code_detection(self):
        rows = [{"item_no": "1", "hs code": "6912.00"}]
        mapping = _auto_detect_pi_mapping(rows)
        assert mapping["hs_code"] == "hs code"

    def test_cbm_detection(self):
        rows = [{"item_no": "1", "cbm": "0.5"}]
        mapping = _auto_detect_pi_mapping(rows)
        assert mapping["cbm"] == "cbm"

    def test_case_insensitive(self):
        """Keys are lowered during matching."""
        rows = [{"Item_No": "1", "Box_L": "10"}]
        mapping = _auto_detect_pi_mapping(rows)
        # The original key is preserved in the mapping value
        assert "item_no" in mapping
        assert "box_L" in mapping


# ── _LLMProviderWrapper ───────────────────────────────────────────────────


class TestLLMProviderWrapper:
    @pytest.mark.asyncio
    async def test_complete_delegates_to_provider(self):
        mock_provider = AsyncMock()
        mock_provider.complete.return_value = "LLM response text"

        wrapper = _LLMProviderWrapper(mock_provider, "gpt-4o")
        result = await wrapper.complete("Extract items from this PO")

        mock_provider.complete.assert_called_once_with(
            model="gpt-4o",
            messages=[{"role": "user", "content": "Extract items from this PO"}],
            temperature=0.0,
            max_tokens=4096,
        )
        assert result == "LLM response text"

    @pytest.mark.asyncio
    async def test_complete_ignores_model_id_param(self):
        """The wrapper always uses its configured model, ignoring model_id."""
        mock_provider = AsyncMock()
        mock_provider.complete.return_value = "response"

        wrapper = _LLMProviderWrapper(mock_provider, "gpt-4o-mini")
        await wrapper.complete("test prompt", model_id="some-other-model")

        # Should use gpt-4o-mini, not some-other-model
        call_kwargs = mock_provider.complete.call_args
        assert call_kwargs.kwargs["model"] == "gpt-4o-mini"


# ── _run_item_extraction ──────────────────────────────────────────────────


class TestRunItemExtraction:
    @pytest.mark.asyncio
    async def test_po_extraction_creates_items(self):
        """PO extraction should call POParserAgent and persist items to DB."""
        from labelforge.agents.base import AgentResult

        mock_result = AgentResult(
            success=True,
            data={"items": [
                {"item_no": "001", "description": "Widget", "upc": "012345678905"},
                {"item_no": "002", "description": "Gadget", "upc": "098765432109"},
            ]},
            confidence=0.92,
        )

        with patch("labelforge.agents.po_parser.POParserAgent") as MockPO, \
             patch("labelforge.core.llm.OpenAIProvider"), \
             patch("labelforge.config.settings") as mock_settings, \
             patch("labelforge.db.session.async_session_factory") as mock_factory:

            # Setup mocks
            mock_settings.openai_api_key = "test-key"
            mock_settings.llm_default_model = "gpt-4o"

            mock_agent = AsyncMock()
            mock_agent.execute.return_value = mock_result
            MockPO.return_value = mock_agent

            # Mock DB session
            mock_db = AsyncMock()
            mock_existing = MagicMock()
            mock_existing.all.return_value = []  # no existing items
            mock_db.execute.return_value = mock_existing
            mock_factory.return_value.__aenter__ = AsyncMock(return_value=mock_db)
            mock_factory.return_value.__aexit__ = AsyncMock(return_value=False)

            # Need to reimport to pick up patched modules
            import importlib
            import labelforge.api.v1.orders as orders_mod
            importlib.reload(orders_mod)

            await orders_mod._run_item_extraction(
                order_id="ORD-001",
                tenant_id="tnt-001",
                doc_class="PURCHASE_ORDER",
                doc_content="Item 001 Widget...",
                filename="PO-test.txt",
            )

            # Verify agent was called
            mock_agent.execute.assert_called_once()
            # Verify items were added to DB
            assert mock_db.add.call_count == 2
            assert mock_db.commit.called

    @pytest.mark.asyncio
    async def test_pi_extraction_creates_items(self):
        """PI extraction should use PIParserAgent with text-to-rows."""
        from labelforge.agents.base import AgentResult

        mock_result = AgentResult(
            success=True,
            data={"items": [
                {"item_no": "A1", "box_L": 10.0, "box_W": 5.0, "box_H": 3.0, "total_cartons": 20},
            ]},
            confidence=0.95,
        )

        with patch("labelforge.agents.pi_parser.PIParserAgent") as MockPI, \
             patch("labelforge.db.session.async_session_factory") as mock_factory:

            mock_agent = AsyncMock()
            mock_agent.execute.return_value = mock_result
            MockPI.return_value = mock_agent

            mock_db = AsyncMock()
            mock_existing = MagicMock()
            mock_existing.all.return_value = []
            mock_db.execute.return_value = mock_existing
            mock_factory.return_value.__aenter__ = AsyncMock(return_value=mock_db)
            mock_factory.return_value.__aexit__ = AsyncMock(return_value=False)

            import importlib
            import labelforge.api.v1.orders as orders_mod
            importlib.reload(orders_mod)

            await orders_mod._run_item_extraction(
                order_id="ORD-001",
                tenant_id="tnt-001",
                doc_class="PROFORMA_INVOICE",
                doc_content="item_no\tbox_l\tbox_w\tbox_h\ttotal_cartons\nA1\t10\t5\t3\t20",
                filename="PI-test.txt",
            )

            mock_agent.execute.assert_called_once()
            assert mock_db.add.call_count == 1

    @pytest.mark.asyncio
    async def test_deduplication_merges_existing_items(self):
        """Items already in the DB should be merged (PI data into PO), not skipped."""
        from labelforge.agents.base import AgentResult

        mock_result = AgentResult(
            success=True,
            data={"items": [
                {"item_no": "001", "box_L": 10.0, "box_W": 5.0},
                {"item_no": "002", "box_L": 20.0, "box_W": 8.0},
            ]},
            confidence=0.90,
        )

        with patch("labelforge.agents.pi_parser.PIParserAgent") as MockPI, \
             patch("labelforge.db.session.async_session_factory") as mock_factory:

            mock_agent = AsyncMock()
            mock_agent.execute.return_value = mock_result
            MockPI.return_value = mock_agent

            # Simulate existing item "001" in DB
            existing_item = MagicMock()
            existing_item.item_no = "001"
            existing_item.data = {"item_no": "001", "upc": "123456"}

            mock_db = AsyncMock()
            mock_scalars = MagicMock()
            mock_scalars.all.return_value = [existing_item]
            mock_execute_result = MagicMock()
            mock_execute_result.scalars.return_value = mock_scalars
            mock_db.execute.return_value = mock_execute_result
            mock_factory.return_value.__aenter__ = AsyncMock(return_value=mock_db)
            mock_factory.return_value.__aexit__ = AsyncMock(return_value=False)

            import importlib
            import labelforge.api.v1.orders as orders_mod
            importlib.reload(orders_mod)

            await orders_mod._run_item_extraction(
                order_id="ORD-001",
                tenant_id="tnt-001",
                doc_class="PROFORMA_INVOICE",
                doc_content="item_no\tbox_l\n001\t10\n002\t20",
                filename="PI.txt",
            )

            # "001" should be merged (data updated), "002" should be added
            assert mock_db.add.call_count == 1  # Only "002" is new
            # Verify the existing item's data was merged with PI fields
            assert existing_item.data["box_L"] == 10.0
            assert existing_item.data["upc"] == "123456"  # Original PO data preserved

    @pytest.mark.asyncio
    async def test_unknown_item_no_skipped(self):
        """Items with empty or 'UNKNOWN' item_no should be skipped."""
        from labelforge.agents.base import AgentResult

        mock_result = AgentResult(
            success=True,
            data={"items": [
                {"item_no": "", "description": "No item number"},
                {"item_no": "UNKNOWN", "description": "Unknown item"},
                {"item_no": "001", "description": "Valid"},
            ]},
            confidence=0.85,
        )

        with patch("labelforge.agents.pi_parser.PIParserAgent") as MockPI, \
             patch("labelforge.db.session.async_session_factory") as mock_factory:

            mock_agent = AsyncMock()
            mock_agent.execute.return_value = mock_result
            MockPI.return_value = mock_agent

            mock_db = AsyncMock()
            mock_scalars = MagicMock()
            mock_scalars.all.return_value = []  # No existing items
            mock_execute_result = MagicMock()
            mock_execute_result.scalars.return_value = mock_scalars
            mock_db.execute.return_value = mock_execute_result
            mock_factory.return_value.__aenter__ = AsyncMock(return_value=mock_db)
            mock_factory.return_value.__aexit__ = AsyncMock(return_value=False)

            import importlib
            import labelforge.api.v1.orders as orders_mod
            importlib.reload(orders_mod)

            await orders_mod._run_item_extraction(
                order_id="ORD-001",
                tenant_id="tnt-001",
                doc_class="PROFORMA_INVOICE",
                doc_content="item_no\tdesc\n\tblank\nUNKNOWN\tunk\n001\tvalid",
                filename="PI.txt",
            )

            # Only "001" should be added
            assert mock_db.add.call_count == 1

    @pytest.mark.asyncio
    async def test_no_items_extracted_does_not_commit(self):
        """When no items are extracted, no DB commit should happen."""
        from labelforge.agents.base import AgentResult

        mock_result = AgentResult(
            success=True,
            data={"items": []},
            confidence=0.50,
        )

        with patch("labelforge.agents.pi_parser.PIParserAgent") as MockPI, \
             patch("labelforge.db.session.async_session_factory") as mock_factory:

            mock_agent = AsyncMock()
            mock_agent.execute.return_value = mock_result
            MockPI.return_value = mock_agent

            mock_db = AsyncMock()
            mock_factory.return_value.__aenter__ = AsyncMock(return_value=mock_db)
            mock_factory.return_value.__aexit__ = AsyncMock(return_value=False)

            import importlib
            import labelforge.api.v1.orders as orders_mod
            importlib.reload(orders_mod)

            await orders_mod._run_item_extraction(
                order_id="ORD-001",
                tenant_id="tnt-001",
                doc_class="PROFORMA_INVOICE",
                doc_content="item_no\nA1",
                filename="PI.txt",
            )

            # No DB interaction for empty results
            assert not mock_db.commit.called

    @pytest.mark.asyncio
    async def test_extraction_error_does_not_raise(self):
        """Agent errors should be caught and logged, not re-raised."""
        with patch("labelforge.agents.po_parser.POParserAgent") as MockPO, \
             patch("labelforge.core.llm.OpenAIProvider"), \
             patch("labelforge.config.settings") as mock_settings:

            mock_settings.openai_api_key = "test"
            mock_settings.llm_default_model = "gpt-4o"

            mock_agent = AsyncMock()
            mock_agent.execute.side_effect = RuntimeError("LLM unavailable")
            MockPO.return_value = mock_agent

            import importlib
            import labelforge.api.v1.orders as orders_mod
            importlib.reload(orders_mod)

            # Should not raise
            await orders_mod._run_item_extraction(
                order_id="ORD-001",
                tenant_id="tnt-001",
                doc_class="PURCHASE_ORDER",
                doc_content="some PO content",
                filename="PO.txt",
            )


# ── _run_ai_classification ────────────────────────────────────────────────


class TestRunAiClassification:
    @pytest.mark.asyncio
    async def test_classification_updates_db(self):
        """Successful classification should update DocumentClassification in DB."""
        from labelforge.agents.base import AgentResult

        mock_cls_result = AgentResult(
            success=True,
            data={"doc_class": "PURCHASE_ORDER"},
            confidence=0.95,
        )

        with patch("labelforge.api.v1.documents.get_blob_store") as mock_store_fn, \
             patch("labelforge.core.doc_extract.extract_text", return_value="PO content"), \
             patch("labelforge.agents.intake_classifier.IntakeClassifierAgent") as MockAgent, \
             patch("labelforge.core.llm.OpenAIProvider"), \
             patch("labelforge.config.settings") as mock_settings, \
             patch("labelforge.db.session.async_session_factory") as mock_factory:

            mock_settings.openai_api_key = "test"
            mock_settings.llm_default_model = "gpt-4o"

            mock_store = AsyncMock()
            mock_store.download.return_value = b"fake content"
            mock_store_fn.return_value = mock_store

            mock_agent = AsyncMock()
            mock_agent.execute.return_value = mock_cls_result
            MockAgent.return_value = mock_agent

            # Mock DB session for classification update
            mock_classification = MagicMock()
            mock_cls_query = MagicMock()
            mock_cls_query.scalar_one_or_none.return_value = mock_classification

            mock_db = AsyncMock()
            mock_db.execute.return_value = mock_cls_query
            mock_factory.return_value.__aenter__ = AsyncMock(return_value=mock_db)
            mock_factory.return_value.__aexit__ = AsyncMock(return_value=False)

            import importlib
            import labelforge.api.v1.orders as orders_mod
            importlib.reload(orders_mod)

            await orders_mod._run_ai_classification(
                doc_id="doc-001",
                tenant_id="tnt-001",
                filename="PO-test.pdf",
                storage_key="ORD-001/PO-test.pdf",
                order_id="",
            )

            # Verify classification was updated
            assert mock_classification.doc_class == "PURCHASE_ORDER"
            assert mock_classification.confidence == 0.95
            assert mock_classification.classification_status == "classified"

    @pytest.mark.asyncio
    async def test_classification_chains_to_extraction_for_po(self):
        """When order_id is set and doc is PO, extraction should be triggered."""
        from labelforge.agents.base import AgentResult

        mock_cls_result = AgentResult(
            success=True,
            data={"doc_class": "PURCHASE_ORDER"},
            confidence=0.95,
        )

        with patch("labelforge.api.v1.documents.get_blob_store") as mock_store_fn, \
             patch("labelforge.core.doc_extract.extract_text", return_value="PO content"), \
             patch("labelforge.agents.intake_classifier.IntakeClassifierAgent") as MockAgent, \
             patch("labelforge.core.llm.OpenAIProvider"), \
             patch("labelforge.config.settings") as mock_settings, \
             patch("labelforge.db.session.async_session_factory") as mock_factory:

            mock_settings.openai_api_key = "test"
            mock_settings.llm_default_model = "gpt-4o"

            mock_store = AsyncMock()
            mock_store.download.return_value = b"fake"
            mock_store_fn.return_value = mock_store

            mock_agent = AsyncMock()
            mock_agent.execute.return_value = mock_cls_result
            MockAgent.return_value = mock_agent

            mock_classification = MagicMock()
            mock_cls_query = MagicMock()
            mock_cls_query.scalar_one_or_none.return_value = mock_classification
            mock_db = AsyncMock()
            mock_db.execute.return_value = mock_cls_query
            mock_factory.return_value.__aenter__ = AsyncMock(return_value=mock_db)
            mock_factory.return_value.__aexit__ = AsyncMock(return_value=False)

            import importlib
            import labelforge.api.v1.orders as orders_mod
            importlib.reload(orders_mod)

            with patch.object(orders_mod, "_run_item_extraction") as mock_extract:
                await orders_mod._run_ai_classification(
                    doc_id="doc-001",
                    tenant_id="tnt-001",
                    filename="PO-test.pdf",
                    storage_key="ORD-001/PO-test.pdf",
                    order_id="ORD-001",
                )

                mock_extract.assert_called_once_with(
                    order_id="ORD-001",
                    tenant_id="tnt-001",
                    doc_class="PURCHASE_ORDER",
                    doc_content="PO content",
                    filename="PO-test.pdf",
                )

    @pytest.mark.asyncio
    async def test_classification_does_not_chain_for_non_po_pi(self):
        """Non-PO/PI documents should not trigger item extraction."""
        from labelforge.agents.base import AgentResult

        mock_cls_result = AgentResult(
            success=True,
            data={"doc_class": "CHECKLIST"},
            confidence=0.88,
        )

        with patch("labelforge.api.v1.documents.get_blob_store") as mock_store_fn, \
             patch("labelforge.core.doc_extract.extract_text", return_value="checklist"), \
             patch("labelforge.agents.intake_classifier.IntakeClassifierAgent") as MockAgent, \
             patch("labelforge.core.llm.OpenAIProvider"), \
             patch("labelforge.config.settings") as mock_settings, \
             patch("labelforge.db.session.async_session_factory") as mock_factory:

            mock_settings.openai_api_key = "test"
            mock_settings.llm_default_model = "gpt-4o"

            mock_store = AsyncMock()
            mock_store.download.return_value = b"fake"
            mock_store_fn.return_value = mock_store

            mock_agent = AsyncMock()
            mock_agent.execute.return_value = mock_cls_result
            MockAgent.return_value = mock_agent

            mock_classification = MagicMock()
            mock_cls_query = MagicMock()
            mock_cls_query.scalar_one_or_none.return_value = mock_classification
            mock_db = AsyncMock()
            mock_db.execute.return_value = mock_cls_query
            mock_factory.return_value.__aenter__ = AsyncMock(return_value=mock_db)
            mock_factory.return_value.__aexit__ = AsyncMock(return_value=False)

            import importlib
            import labelforge.api.v1.orders as orders_mod
            importlib.reload(orders_mod)

            with patch.object(orders_mod, "_run_item_extraction") as mock_extract:
                await orders_mod._run_ai_classification(
                    doc_id="doc-001",
                    tenant_id="tnt-001",
                    filename="checklist.pdf",
                    storage_key="ORD-001/checklist.pdf",
                    order_id="ORD-001",
                )

                mock_extract.assert_not_called()

    @pytest.mark.asyncio
    async def test_classification_failure_still_marks_classified(self):
        """If agent raises, status should still become 'classified' (error recovery)."""
        with patch("labelforge.api.v1.documents.get_blob_store") as mock_store_fn, \
             patch("labelforge.core.doc_extract.extract_text", return_value="content"), \
             patch("labelforge.agents.intake_classifier.IntakeClassifierAgent") as MockAgent, \
             patch("labelforge.core.llm.OpenAIProvider"), \
             patch("labelforge.config.settings") as mock_settings, \
             patch("labelforge.db.session.async_session_factory") as mock_factory:

            mock_settings.openai_api_key = "test"
            mock_settings.llm_default_model = "gpt-4o"

            mock_store = AsyncMock()
            mock_store.download.return_value = b"fake"
            mock_store_fn.return_value = mock_store

            mock_agent = AsyncMock()
            mock_agent.execute.side_effect = RuntimeError("API down")
            MockAgent.return_value = mock_agent

            mock_classification = MagicMock()
            mock_cls_query = MagicMock()
            mock_cls_query.scalar_one_or_none.return_value = mock_classification
            mock_db = AsyncMock()
            mock_db.execute.return_value = mock_cls_query
            mock_factory.return_value.__aenter__ = AsyncMock(return_value=mock_db)
            mock_factory.return_value.__aexit__ = AsyncMock(return_value=False)

            import importlib
            import labelforge.api.v1.orders as orders_mod
            importlib.reload(orders_mod)

            # Should not raise
            await orders_mod._run_ai_classification(
                doc_id="doc-001",
                tenant_id="tnt-001",
                filename="test.pdf",
                storage_key="ORD-001/test.pdf",
            )

            assert mock_classification.classification_status == "classified"


# ── Preview dual auth ─────────────────────────────────────────────────────


class TestPreviewDualAuth:
    """Test preview endpoint with both auth methods."""

    def test_preview_with_header_auth(self, client, admin_headers):
        """Standard Authorization header should work."""
        resp = client.get("/api/v1/documents/doc-001/preview", headers=admin_headers)
        # Will be 404 (file not in blob store) but NOT 401
        assert resp.status_code in (200, 404)

    def test_preview_with_query_token(self, client, admin_token):
        """Query param ?token= should work for browser tabs."""
        resp = client.get(f"/api/v1/documents/doc-001/preview?token={admin_token}")
        # Will be 404 (file not in blob store) but NOT 401
        assert resp.status_code in (200, 404)

    def test_preview_no_auth_returns_401(self, client):
        """No auth at all should return 401."""
        resp = client.get("/api/v1/documents/doc-001/preview")
        assert resp.status_code == 401

    def test_preview_invalid_token_returns_401(self, client):
        """Invalid JWT should return 401."""
        resp = client.get("/api/v1/documents/doc-001/preview?token=invalid.jwt.token")
        assert resp.status_code == 401

    def test_preview_header_takes_priority(self, client, admin_headers, admin_token):
        """When both header and query param are provided, header wins."""
        resp = client.get(
            f"/api/v1/documents/doc-001/preview?token=bad.token.here",
            headers=admin_headers,
        )
        # Header is valid, so we should get past auth (404 for missing blob is OK)
        assert resp.status_code in (200, 404)


# ── Upload to order endpoint ──────────────────────────────────────────────


class TestUploadOrderDocument:
    def test_upload_to_valid_order(self, client, admin_headers):
        resp = client.post(
            "/api/v1/orders/ORD-2026-0042/documents",
            files={"file": ("PO-new.pdf", b"test content", "application/pdf")},
            headers=admin_headers,
        )
        assert resp.status_code == 201
        data = resp.json()
        assert data["order_id"] == "ORD-2026-0042"
        assert data["filename"] == "PO-new.pdf"
        assert data["classification_status"] in ("pending", "classifying")
        assert data["size_bytes"] > 0

    def test_upload_to_nonexistent_order(self, client, admin_headers):
        resp = client.post(
            "/api/v1/orders/ORD-NONEXISTENT/documents",
            files={"file": ("test.pdf", b"content", "application/pdf")},
            headers=admin_headers,
        )
        assert resp.status_code == 404

    def test_upload_empty_file_rejected(self, client, admin_headers):
        resp = client.post(
            "/api/v1/orders/ORD-2026-0042/documents",
            files={"file": ("empty.pdf", b"", "application/pdf")},
            headers=admin_headers,
        )
        assert resp.status_code == 400

    def test_upload_requires_auth(self, client):
        resp = client.post(
            "/api/v1/orders/ORD-2026-0042/documents",
            files={"file": ("test.pdf", b"content", "application/pdf")},
        )
        assert resp.status_code == 401

    def test_upload_classification_status_is_classifying(self, client, admin_headers):
        """Newly uploaded documents should start with 'classifying' status."""
        resp = client.post(
            "/api/v1/orders/ORD-2026-0042/documents",
            files={"file": ("PO-test.pdf", b"content", "application/pdf")},
            headers=admin_headers,
        )
        assert resp.status_code == 201
        assert resp.json()["classification_status"] == "classifying"

    def test_upload_filename_classification(self, client, admin_headers):
        """Filename heuristic should provide quick classification."""
        cases = [
            ("PO-12345.pdf", "PURCHASE_ORDER"),
            ("proforma-invoice.pdf", "PROFORMA_INVOICE"),
            ("warning-labels.pdf", "WARNING_LABELS"),
        ]
        for filename, expected_class in cases:
            resp = client.post(
                "/api/v1/orders/ORD-2026-0042/documents",
                files={"file": (filename, b"content", "application/pdf")},
                headers=admin_headers,
            )
            assert resp.status_code == 201
            assert resp.json()["doc_class"] == expected_class, f"Failed for {filename}"


# ── OrderItem.data field ──────────────────────────────────────────────────


class TestOrderItemDataField:
    def test_order_item_data_field_in_contract(self):
        """OrderItem contract model should accept data field."""
        from labelforge.contracts.models import OrderItem
        from datetime import datetime, timezone

        item = OrderItem(
            id="itm-001",
            order_id="ORD-001",
            item_no="001",
            state="PARSED",
            state_changed_at=datetime.now(timezone.utc),
            data={"description": "Widget", "upc": "012345678905", "total_qty": 100},
        )
        assert item.data is not None
        assert item.data["description"] == "Widget"
        assert item.data["upc"] == "012345678905"

    def test_order_item_data_field_optional(self):
        """data should default to None when not provided."""
        from labelforge.contracts.models import OrderItem
        from datetime import datetime, timezone

        item = OrderItem(
            id="itm-001",
            order_id="ORD-001",
            item_no="001",
            state="CREATED",
            state_changed_at=datetime.now(timezone.utc),
        )
        assert item.data is None

    def test_order_detail_includes_item_data(self, client, admin_headers):
        """GET /orders/{id} items should include data field."""
        # Get an order that has items
        resp = client.get("/api/v1/orders", headers=admin_headers)
        if resp.status_code == 200 and resp.json()["orders"]:
            order_id = resp.json()["orders"][0]["id"]
            detail = client.get(f"/api/v1/orders/{order_id}", headers=admin_headers)
            if detail.status_code == 200:
                for item in detail.json().get("items", []):
                    # data field should be present (even if null)
                    assert "data" in item


# ── Classification status transitions ─────────────────────────────────────


class TestClassificationStatusTransitions:
    def test_upload_sets_classifying_status(self, client, admin_headers):
        """Upload should set classification_status to 'classifying'."""
        resp = client.post(
            "/api/v1/documents/upload",
            params={"order_id": "ORD-2026-0042"},
            files={"file": ("test-doc.pdf", b"content", "application/pdf")},
            headers=admin_headers,
        )
        assert resp.status_code == 201
        assert resp.json()["classification_status"] in ("pending", "classifying")

    def test_seed_data_has_classified_status(self, client, admin_headers):
        """Seed documents should have 'classified' status."""
        resp = client.get(
            "/api/v1/documents",
            params={"classification_status": "classified"},
            headers=admin_headers,
        )
        assert resp.status_code == 200
        docs = resp.json()["documents"]
        for doc in docs:
            assert doc["classification_status"] == "classified"


# ── documents.py delegation to orders.py ──────────────────────────────────


class TestDocumentsClassificationDelegation:
    @pytest.mark.asyncio
    async def test_documents_delegates_to_orders(self):
        """documents._run_ai_classification should delegate to orders._run_ai_classification."""
        with patch("labelforge.api.v1.orders._run_ai_classification") as mock_orders_classify:
            mock_orders_classify.return_value = None

            from labelforge.api.v1.documents import _run_ai_classification
            await _run_ai_classification(
                doc_id="doc-test",
                tenant_id="tnt-001",
                filename="test.pdf",
                storage_key="ORD-001/test.pdf",
                order_id="ORD-001",
            )

            mock_orders_classify.assert_called_once_with(
                doc_id="doc-test",
                tenant_id="tnt-001",
                filename="test.pdf",
                storage_key="ORD-001/test.pdf",
                order_id="ORD-001",
            )
