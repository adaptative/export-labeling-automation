"""Seed the database with initial data for development.

Idempotent: only inserts if the tenants table is empty.
"""
from __future__ import annotations

import hashlib
from datetime import datetime, timezone

from sqlalchemy import select

from labelforge.db.session import async_session_factory
from labelforge.db.models import (
    Tenant, User, Importer, ImporterProfileModel,
    Order, OrderItemModel, Document, DocumentClassification,
    ComplianceRule, WarningLabel, Artifact,
    HiTLThreadModel, HiTLMessageModel, CostEvent,
    AuditLog, Notification, SSOConfig, BudgetTier, BreakerEvent,
)


_T = "tnt-nakoda-001"  # default tenant id


async def seed_if_empty() -> None:
    """Insert seed data if the database is empty."""
    async with async_session_factory() as session:
        result = await session.execute(select(Tenant).limit(1))
        if result.scalar_one_or_none() is not None:
            return  # already seeded

        # ── Tenant ──
        session.add(Tenant(id=_T, name="Nakoda Art & Craft", slug="nakoda"))

        # ── Users ──
        users = [
            User(id="usr-admin-001", tenant_id=_T, email="admin@nakodacraft.com",
                 display_name="Admin User", role="ADMIN",
                 hashed_password=hashlib.sha256(b"admin123").hexdigest(),
                 is_active=True, last_active=_dt(2026, 4, 12, 10)),
            User(id="usr-ops-001", tenant_id=_T, email="ops@nakodacraft.com",
                 display_name="Ops Manager", role="OPS",
                 hashed_password=hashlib.sha256(b"ops123").hexdigest(),
                 is_active=True, last_active=_dt(2026, 4, 11, 16, 30)),
            User(id="usr-comp-001", tenant_id=_T, email="compliance@nakodacraft.com",
                 display_name="Compliance Officer", role="COMPLIANCE",
                 hashed_password=hashlib.sha256(b"comp123").hexdigest(),
                 is_active=True, last_active=_dt(2026, 4, 10, 14, 15)),
            User(id="usr-ext-001", tenant_id=_T, email="importer@acme.com",
                 display_name="Acme Importer", role="EXTERNAL",
                 hashed_password=hashlib.sha256(b"portal123").hexdigest(),
                 is_active=True, last_active=_dt(2026, 4, 9, 11)),
        ]
        session.add_all(users)

        # ── Importers ──
        importers = [
            Importer(id="IMP-ACME", tenant_id=_T, name="Acme Trading Co.", code="ACME"),
            Importer(id="IMP-GLOBEX", tenant_id=_T, name="Globex Corporation", code="GLOBEX"),
            Importer(id="IMP-INITECH", tenant_id=_T, name="Initech Inc.", code="INITECH"),
        ]
        session.add_all(importers)

        # ── Importer Profiles ──
        profiles = [
            ImporterProfileModel(
                id="prof-acme-v3", importer_id="IMP-ACME", tenant_id=_T, version=3,
                brand_treatment={"primary_color": "#003DA5", "font_family": "Helvetica Neue", "logo_position": "top-right"},
                panel_layouts={"carton_top": ["logo", "upc", "item_description"], "carton_side": ["warnings", "country_of_origin", "net_weight"]},
                handling_symbol_rules={"fragile": True, "this_side_up": True, "keep_dry": False},
                pi_template_mapping={"item_no_col": "A", "box_dims_col": "D", "cbm_col": "G"},
                logo_asset_hash="sha256:a1b2c3d4e5f6",
            ),
            ImporterProfileModel(
                id="prof-globex-v2", importer_id="IMP-GLOBEX", tenant_id=_T, version=2,
                brand_treatment={"primary_color": "#E31837", "font_family": "Arial", "logo_position": "top-left"},
                panel_layouts={"carton_top": ["logo", "item_description", "upc"], "carton_side": ["net_weight", "warnings", "country_of_origin"]},
                handling_symbol_rules={"fragile": False, "this_side_up": True, "keep_dry": True},
                pi_template_mapping={"item_no_col": "B", "box_dims_col": "E", "cbm_col": "H"},
                logo_asset_hash="sha256:f6e5d4c3b2a1",
            ),
            ImporterProfileModel(
                id="prof-initech-v1", importer_id="IMP-INITECH", tenant_id=_T, version=1,
                brand_treatment={"primary_color": "#2E8B57", "font_family": "Roboto", "logo_position": "center"},
                panel_layouts={"carton_top": ["logo", "upc"], "carton_side": ["item_description", "warnings"]},
                handling_symbol_rules={"fragile": True, "this_side_up": False, "keep_dry": False},
            ),
        ]
        session.add_all(profiles)

        # ── Orders ──
        orders = [
            Order(id="ORD-2026-0042", tenant_id=_T, importer_id="IMP-ACME", po_number="PO-88210",
                  created_at=_dt(2026, 4, 8, 9), updated_at=_dt(2026, 4, 10, 14, 30)),
            Order(id="ORD-2026-0043", tenant_id=_T, importer_id="IMP-GLOBEX", po_number="PO-77301",
                  created_at=_dt(2026, 4, 5, 11), updated_at=_dt(2026, 4, 9, 16)),
            Order(id="ORD-2026-0044", tenant_id=_T, importer_id="IMP-ACME", po_number="PO-88215",
                  created_at=_dt(2026, 4, 9, 8), updated_at=_dt(2026, 4, 10, 14, 30)),
            Order(id="ORD-2026-0045", tenant_id=_T, importer_id="IMP-GLOBEX", po_number="PO-90001",
                  created_at=_dt(2026, 4, 10, 7), updated_at=_dt(2026, 4, 12, 10)),
        ]
        session.add_all(orders)

        # ── Order Items ──
        items = [
            OrderItemModel(id="item-001", order_id="ORD-2026-0042", tenant_id=_T,
                          item_no="A1001", state="COMPLIANCE_EVAL", rules_snapshot_id="snap-r1",
                          state_changed_at=_dt(2026, 4, 10, 14, 30)),
            OrderItemModel(id="item-002", order_id="ORD-2026-0042", tenant_id=_T,
                          item_no="A1002", state="FUSED", rules_snapshot_id="snap-r1",
                          state_changed_at=_dt(2026, 4, 10, 14, 30)),
            OrderItemModel(id="item-003", order_id="ORD-2026-0043", tenant_id=_T,
                          item_no="B2001", state="DELIVERED", rules_snapshot_id="snap-r2",
                          state_changed_at=_dt(2026, 4, 9, 16)),
            OrderItemModel(id="item-004", order_id="ORD-2026-0044", tenant_id=_T,
                          item_no="C3001", state="HUMAN_BLOCKED", rules_snapshot_id="snap-r3",
                          state_changed_at=_dt(2026, 4, 10, 14, 30)),
            OrderItemModel(id="item-005", order_id="ORD-2026-0044", tenant_id=_T,
                          item_no="C3002", state="FUSED", rules_snapshot_id="snap-r3",
                          state_changed_at=_dt(2026, 4, 10, 12)),
            OrderItemModel(id="item-006", order_id="ORD-2026-0044", tenant_id=_T,
                          item_no="C3003", state="PARSED", rules_snapshot_id="snap-r3",
                          state_changed_at=_dt(2026, 4, 10, 11)),
            # ORD-2026-0045 items (5 items, mostly progressed)
            OrderItemModel(id="item-007", order_id="ORD-2026-0045", tenant_id=_T,
                          item_no="D4001", state="VALIDATED",
                          state_changed_at=_dt(2026, 4, 12, 8)),
            OrderItemModel(id="item-008", order_id="ORD-2026-0045", tenant_id=_T,
                          item_no="D4002", state="VALIDATED",
                          state_changed_at=_dt(2026, 4, 12, 9)),
            OrderItemModel(id="item-009", order_id="ORD-2026-0045", tenant_id=_T,
                          item_no="D4003", state="COMPOSED",
                          state_changed_at=_dt(2026, 4, 12, 7)),
            OrderItemModel(id="item-010", order_id="ORD-2026-0045", tenant_id=_T,
                          item_no="D4004", state="REVIEWED",
                          state_changed_at=_dt(2026, 4, 12, 10)),
            OrderItemModel(id="item-011", order_id="ORD-2026-0045", tenant_id=_T,
                          item_no="D4005", state="REVIEWED",
                          state_changed_at=_dt(2026, 4, 12, 10)),
        ]
        session.add_all(items)

        # ── Documents ──
        docs = [
            Document(id="doc-001", tenant_id=_T, order_id="ORD-2026-0042",
                     filename="PO-88210.pdf", s3_key="docs/ORD-2026-0042/PO-88210.pdf",
                     size_bytes=524288, uploaded_at=_dt(2026, 4, 8, 9, 5)),
            Document(id="doc-002", tenant_id=_T, order_id="ORD-2026-0042",
                     filename="PI-88210.pdf", s3_key="docs/ORD-2026-0042/PI-88210.pdf",
                     size_bytes=262144, uploaded_at=_dt(2026, 4, 8, 9, 6)),
            Document(id="doc-003", tenant_id=_T, order_id="ORD-2026-0043",
                     filename="PO-77301.pdf", s3_key="docs/ORD-2026-0043/PO-77301.pdf",
                     size_bytes=393216, uploaded_at=_dt(2026, 4, 5, 11, 10)),
            Document(id="doc-004", tenant_id=_T, order_id="ORD-2026-0044",
                     filename="warning-labels-batch.pdf", s3_key="docs/ORD-2026-0044/warning-labels-batch.pdf",
                     size_bytes=131072, uploaded_at=_dt(2026, 4, 9, 8, 30)),
        ]
        session.add_all(docs)

        doc_classes = [
            DocumentClassification(id="dc-001", document_id="doc-001", tenant_id=_T,
                                   doc_class="PURCHASE_ORDER", confidence=0.98, classification_status="classified"),
            DocumentClassification(id="dc-002", document_id="doc-002", tenant_id=_T,
                                   doc_class="PROFORMA_INVOICE", confidence=0.96, classification_status="classified"),
            DocumentClassification(id="dc-003", document_id="doc-003", tenant_id=_T,
                                   doc_class="PURCHASE_ORDER", confidence=0.97, classification_status="classified"),
            DocumentClassification(id="dc-004", document_id="doc-004", tenant_id=_T,
                                   doc_class="WARNING_LABELS", confidence=0.91, classification_status="classified"),
        ]
        session.add_all(doc_classes)

        # ── Compliance Rules ──
        rules = [
            ComplianceRule(id="rule-001", tenant_id=_T, rule_code="PROP65", version=3,
                          title="California Proposition 65 Warning",
                          description="Products containing chemicals known to the State of California to cause cancer or reproductive harm must carry a Prop 65 warning label.",
                          region="US-CA", placement="product", is_active=True,
                          updated_at=_dt(2026, 3, 1)),
            ComplianceRule(id="rule-002", tenant_id=_T, rule_code="CPSIA", version=2,
                          title="CPSIA Lead & Phthalate Tracking",
                          description="Children's products must include tracking labels per the Consumer Product Safety Improvement Act.",
                          region="US", placement="both", is_active=True,
                          updated_at=_dt(2026, 2, 15)),
            ComplianceRule(id="rule-003", tenant_id=_T, rule_code="FCC15", version=1,
                          title="FCC Part 15 Declaration",
                          description="Electronic devices must carry the FCC Part 15 compliance statement on the carton.",
                          region="US", placement="carton", is_active=True,
                          updated_at=_dt(2026, 1, 20)),
            ComplianceRule(id="rule-004", tenant_id=_T, rule_code="CHOKING_HAZARD", version=2,
                          title="Small Parts Choking Hazard Warning",
                          description="Toys and children's products with small parts must include ASTM F963 choking hazard warning.",
                          region="US", placement="both", is_active=True,
                          updated_at=_dt(2026, 3, 10)),
            ComplianceRule(id="rule-005", tenant_id=_T, rule_code="COUNTRY_OF_ORIGIN", version=1,
                          title="Country of Origin Marking",
                          description="All imported goods must be marked with the country of origin per 19 CFR 134.",
                          region="US", placement="carton", is_active=True,
                          updated_at=_dt(2025, 12, 1)),
        ]
        session.add_all(rules)

        # ── Warning Labels ──
        labels = [
            WarningLabel(id="wl-001", tenant_id=_T, code="PROP65_CANCER",
                        title="Proposition 65 Cancer Warning",
                        text_en="WARNING: This product can expose you to chemicals including lead, which is known to the State of California to cause cancer.",
                        region="US-CA", placement="product", icon_asset_hash="sha256:prop65icon01",
                        updated_at=_dt(2026, 3, 1)),
            WarningLabel(id="wl-002", tenant_id=_T, code="PROP65_REPRO",
                        title="Proposition 65 Reproductive Harm Warning",
                        text_en="WARNING: This product can expose you to chemicals including DEHP, which is known to the State of California to cause birth defects or other reproductive harm.",
                        region="US-CA", placement="product", icon_asset_hash="sha256:prop65icon02",
                        updated_at=_dt(2026, 3, 1)),
            WarningLabel(id="wl-003", tenant_id=_T, code="CHOKING_SMALL_PARTS",
                        title="Choking Hazard - Small Parts",
                        text_en="WARNING: CHOKING HAZARD - Small parts. Not for children under 3 years.",
                        region="US", placement="both", icon_asset_hash="sha256:chokingicon01",
                        updated_at=_dt(2026, 2, 15)),
            WarningLabel(id="wl-004", tenant_id=_T, code="CHOKING_SMALL_BALL",
                        title="Choking Hazard - Small Ball",
                        text_en="WARNING: CHOKING HAZARD - This toy is a small ball. Not for children under 3 years.",
                        region="US", placement="both", icon_asset_hash="sha256:chokingicon02",
                        updated_at=_dt(2026, 2, 15)),
            WarningLabel(id="wl-005", tenant_id=_T, code="FCC_PART15",
                        title="FCC Part 15 Compliance Statement",
                        text_en="This device complies with Part 15 of the FCC Rules.",
                        region="US", placement="carton",
                        updated_at=_dt(2026, 1, 20)),
        ]
        session.add_all(labels)

        # ── Artifacts ──
        artifacts = [
            Artifact(id="art-001", tenant_id=_T, order_item_id="item-001",
                    artifact_type="fused_item", s3_key="artifacts/art-001/fused_item.json",
                    content_hash="sha256:abcdef1234567890", size_bytes=245760, mime_type="application/json",
                    provenance={
                        "model_id": "gpt-5.4", "prompt_hash": "sha256:prompt001",
                        "steps": [
                            {"step_number": 1, "agent_id": "extractor-agent-v2", "model_id": "gpt-5.4",
                             "prompt_hash": "sha256:ext001", "input_hash": "sha256:po001",
                             "output_hash": "sha256:extracted001", "action": "extract",
                             "timestamp": "2026-04-08T09:30:00Z", "duration_ms": 4200},
                            {"step_number": 2, "agent_id": "composer-agent-v3", "model_id": "gpt-5.4",
                             "prompt_hash": "sha256:prompt001", "input_hash": "sha256:extracted001",
                             "output_hash": "sha256:abcdef1234567890", "action": "compose",
                             "timestamp": "2026-04-08T09:45:00Z", "duration_ms": 8500},
                            {"step_number": 3, "agent_id": "validator-agent-v2", "model_id": "gpt-5.4",
                             "prompt_hash": "sha256:val001", "input_hash": "sha256:abcdef1234567890",
                             "output_hash": "sha256:abcdef1234567890", "action": "validate",
                             "timestamp": "2026-04-08T10:00:00Z", "duration_ms": 3100},
                        ],
                    },
                    created_at=_dt(2026, 4, 8, 10)),
            Artifact(id="art-002", tenant_id=_T, order_item_id="item-001",
                    artifact_type="compliance_report", s3_key="artifacts/art-002/compliance_report.pdf",
                    content_hash="sha256:fedcba0987654321", size_bytes=1048576, mime_type="application/pdf",
                    provenance={"model_id": "gpt-5.4", "prompt_hash": "sha256:prompt002"},
                    created_at=_dt(2026, 4, 8, 10, 30)),
            Artifact(id="art-003", tenant_id=_T, order_item_id="item-003",
                    artifact_type="die_cut_svg", s3_key="artifacts/art-003/diecut.svg",
                    content_hash="sha256:1122334455667788", size_bytes=82944, mime_type="image/svg+xml",
                    provenance=None,
                    created_at=_dt(2026, 4, 9, 8)),
        ]
        session.add_all(artifacts)

        # ── HiTL Threads ──
        threads = [
            HiTLThreadModel(id="hitl-001", tenant_id=_T, order_id="ORD-2026-0042",
                           item_no="A1001", agent_id="compliance-agent", priority="P0", status="OPEN",
                           sla_deadline=_dt(2026, 4, 11, 14, 30),
                           created_at=_dt(2026, 4, 10, 14, 30)),
            HiTLThreadModel(id="hitl-002", tenant_id=_T, order_id="ORD-2026-0044",
                           item_no="C3001", agent_id="fusion-agent", priority="P1", status="IN_PROGRESS",
                           sla_deadline=_dt(2026, 4, 12, 9),
                           created_at=_dt(2026, 4, 9, 10)),
            HiTLThreadModel(id="hitl-003", tenant_id=_T, order_id="ORD-2026-0043",
                           item_no="B2001", agent_id="validation-agent", priority="P2", status="RESOLVED",
                           created_at=_dt(2026, 4, 6, 15)),
        ]
        session.add_all(threads)

        messages = [
            HiTLMessageModel(id="msg-001", thread_id="hitl-001", tenant_id=_T,
                            sender_type="agent",
                            content="Prop 65 warning required for item A1001 but the destination state could not be determined. Please confirm the US destination state.",
                            context={"rule_code": "PROP65", "item_no": "A1001"},
                            created_at=_dt(2026, 4, 10, 14, 30)),
            HiTLMessageModel(id="msg-002", thread_id="hitl-001", tenant_id=_T,
                            sender_type="human",
                            content="Destination is California. Please apply Prop 65 warning label.",
                            created_at=_dt(2026, 4, 10, 15)),
            HiTLMessageModel(id="msg-003", thread_id="hitl-002", tenant_id=_T,
                            sender_type="agent",
                            content="PO line item C3001 lists net weight as 2.5 kg but PI shows 3.1 kg. Which value is correct?",
                            context={"field": "net_weight", "po_value": "2.5", "pi_value": "3.1"},
                            created_at=_dt(2026, 4, 9, 10, 5)),
        ]
        session.add_all(messages)

        # ── Cost Events ──
        cost_events = [
            CostEvent(id="ce-001", tenant_id=_T, scope="llm_inference", amount_usd=184.22,
                     model_id="gpt-5.4", input_tokens=850000, output_tokens=120000,
                     created_at=_dt(2026, 4, 12, 14)),
            CostEvent(id="ce-002", tenant_id=_T, scope="llm_inference", amount_usd=165.80,
                     model_id="gpt-5.4", input_tokens=780000, output_tokens=98000,
                     created_at=_dt(2026, 4, 11, 14)),
        ]
        session.add_all(cost_events)

        # ── Audit Log ──
        audit_entries = [
            AuditLog(id="aud-001", tenant_id=_T, actor="sarah.chen@nakoda.com", actor_type="user",
                    action="APPROVE", resource_type="order", resource_id="PO-2065",
                    detail="Approved compliance report for PO-2065", ip_address="10.0.1.42",
                    details={"previous_status": "pending", "new_status": "approved"},
                    created_at=_dt(2026, 4, 12, 14, 32)),
            AuditLog(id="aud-002", tenant_id=_T, actor="composer-agent-v3", actor_type="agent",
                    action="GENERATE", resource_type="artifact", resource_id="art-001",
                    detail="Generated fused item SVG for PO-2065", ip_address="10.0.2.10",
                    created_at=_dt(2026, 4, 12, 14, 28)),
            AuditLog(id="aud-003", tenant_id=_T, actor="validator-agent-v2", actor_type="agent",
                    action="VALIDATE", resource_type="compliance_report", resource_id="rpt-012",
                    detail="Validated Prop 65 compliance for PO-2065", ip_address="10.0.2.11",
                    created_at=_dt(2026, 4, 12, 14, 15)),
            AuditLog(id="aud-004", tenant_id=_T, actor="system", actor_type="system",
                    action="CREATE", resource_type="order", resource_id="PO-2070",
                    detail="Order PO-2070 created from EDI import", ip_address="10.0.0.1",
                    created_at=_dt(2026, 4, 12, 13, 50)),
            AuditLog(id="aud-005", tenant_id=_T, actor="mike.johnson@nakoda.com", actor_type="user",
                    action="UPDATE", resource_type="rule", resource_id="rule-003",
                    detail="Updated furniture tip-over height threshold from 30 to 27 inches", ip_address="10.0.1.55",
                    details={"field": "height_inches", "old_value": 30, "new_value": 27},
                    created_at=_dt(2026, 4, 12, 13, 45)),
            AuditLog(id="aud-006", tenant_id=_T, actor="classifier-agent-v1", actor_type="agent",
                    action="CLASSIFY", resource_type="document", resource_id="doc-445",
                    detail="Classified invoice as commercial_invoice with 98% confidence", ip_address="10.0.2.12",
                    created_at=_dt(2026, 4, 12, 12, 30)),
            AuditLog(id="aud-007", tenant_id=_T, actor="sarah.chen@nakoda.com", actor_type="user",
                    action="REJECT", resource_type="artifact", resource_id="art-008",
                    detail="Rejected die-cut: incorrect bleed margins", ip_address="10.0.1.42",
                    created_at=_dt(2026, 4, 12, 11, 20)),
            AuditLog(id="aud-008", tenant_id=_T, actor="extractor-agent-v2", actor_type="agent",
                    action="EXTRACT", resource_type="document", resource_id="doc-440",
                    detail="Extracted 24 line items from packing list", ip_address="10.0.2.13",
                    created_at=_dt(2026, 4, 11, 16, 45)),
            AuditLog(id="aud-009", tenant_id=_T, actor="system", actor_type="system",
                    action="CREATE", resource_type="notification", resource_id="ntf-120",
                    detail="Sent compliance alert to importer", ip_address="10.0.0.1",
                    created_at=_dt(2026, 4, 11, 15, 30)),
            AuditLog(id="aud-010", tenant_id=_T, actor="admin@nakoda.com", actor_type="user",
                    action="UPDATE", resource_type="user", resource_id="usr-005",
                    detail="Changed role from OPS to COMPLIANCE", ip_address="10.0.1.10",
                    details={"old_role": "OPS", "new_role": "COMPLIANCE"},
                    created_at=_dt(2026, 4, 11, 14)),
        ]
        session.add_all(audit_entries)

        # ── Notifications ──
        notifications = [
            Notification(id="notif-001", tenant_id=_T, type="hitl_escalation",
                        title="HiTL Escalation: Prop 65 warning needed",
                        body="Item A1001 in order ORD-2026-0042 requires human input to determine if Prop 65 warning applies.",
                        level="high", order_id="ORD-2026-0042", item_no="A1001",
                        created_at=_dt(2026, 4, 10, 14, 30)),
            Notification(id="notif-002", tenant_id=_T, type="compliance_fail",
                        title="Compliance check failed for item C3001",
                        body="FCC Part 15 declaration missing from carton layout for item C3001.",
                        level="high", order_id="ORD-2026-0044", item_no="C3001",
                        created_at=_dt(2026, 4, 9, 16)),
            Notification(id="notif-003", tenant_id=_T, type="order_delivered",
                        title="Order ORD-2026-0043 delivered",
                        body="All items in order ORD-2026-0043 have been marked as delivered.",
                        level="info", order_id="ORD-2026-0043", is_read=True,
                        created_at=_dt(2026, 4, 9, 16)),
            Notification(id="notif-004", tenant_id=_T, type="fusion_conflict",
                        title="Data conflict detected during fusion",
                        body="Net weight mismatch between PO (2.5 kg) and PI (3.1 kg) for item C3001.",
                        level="medium", order_id="ORD-2026-0044", item_no="C3001",
                        created_at=_dt(2026, 4, 9, 10, 5)),
        ]
        session.add_all(notifications)

        # ── SSO Config ──
        session.add(SSOConfig(id="sso-001", tenant_id=_T))

        # ── Budget Tiers ──
        tiers = [
            BudgetTier(id="llm_inference", tenant_id=_T, name="LLM Inference", cap=1000.0, unit="$/day"),
            BudgetTier(id="api_calls", tenant_id=_T, name="API Calls", cap=10000, unit="calls/hour"),
            BudgetTier(id="storage", tenant_id=_T, name="Storage", cap=100.0, unit="GB"),
            BudgetTier(id="hitl", tenant_id=_T, name="Human Review (HiTL)", cap=80.0, unit="hours/month"),
        ]
        session.add_all(tiers)

        breaker_events = [
            BreakerEvent(id="evt-001", tenant_id=_T, tier_id="llm_inference",
                        event_type="breach", triggered_by="cost_breaker_01",
                        action="Paused new inferences", status="resolved",
                        created_at=_dt(2026, 4, 12, 14, 5)),
            BreakerEvent(id="evt-002", tenant_id=_T, tier_id="llm_inference",
                        event_type="recovery", triggered_by="cost_breaker_01",
                        action="Resumed inferences", status="resolved",
                        created_at=_dt(2026, 4, 12, 14, 35)),
            BreakerEvent(id="evt-003", tenant_id=_T, tier_id="api_calls",
                        event_type="breach", triggered_by="rate_limiter_02",
                        action="Throttled API requests", status="resolved",
                        created_at=_dt(2026, 4, 11, 9, 12)),
            BreakerEvent(id="evt-004", tenant_id=_T, tier_id="api_calls",
                        event_type="recovery", triggered_by="rate_limiter_02",
                        action="Restored normal rate", status="resolved",
                        created_at=_dt(2026, 4, 11, 9, 42)),
        ]
        session.add_all(breaker_events)

        await session.commit()


def _dt(year: int, month: int, day: int, hour: int = 0, minute: int = 0) -> datetime:
    return datetime(year, month, day, hour, minute, 0, tzinfo=timezone.utc)
