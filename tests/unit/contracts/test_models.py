"""Comprehensive unit tests for labelforge.contracts.models (TASK-047)."""

from datetime import datetime

import pytest
from pydantic import ValidationError

from labelforge.contracts.models import (
    ApprovalPDFInput,
    ComplianceReport,
    DieCutInput,
    DocumentClass,
    FrozenInputs,
    FusedItem,
    FusionIssue,
    FusionResult,
    HiTLMessage,
    HiTLThread,
    ImporterProfile,
    ItemState,
    LLMSnapshot,
    OrderItem,
    OrderState,
    PILineItem,
    POLineItem,
    Provenance,
    RuleVerdict,
    ValidationReport,
    compute_order_state,
)

# ── Valid UPC constants ────────────────────────────────────────────────────────
VALID_UPC = "012345678905"  # passes Luhn-like check
VALID_UPC_2 = "614141000036"


# ── Helpers ────────────────────────────────────────────────────────────────────


def _make_po_line(**overrides) -> POLineItem:
    defaults = dict(
        item_no="1",
        upc=VALID_UPC,
        description="Widget",
        case_qty="12",
        total_qty=100,
        confidence=0.95,
    )
    defaults.update(overrides)
    return POLineItem(**defaults)


def _make_fused_item(**overrides) -> FusedItem:
    defaults = dict(
        item_no="1",
        upc=VALID_UPC,
        description="Widget",
        case_qty="12",
        box_L=10.0,
        box_W=8.0,
        box_H=6.0,
        total_qty=100,
        total_cartons=10,
        confidence=0.9,
    )
    defaults.update(overrides)
    return FusedItem(**defaults)


def _make_compliance_report(**overrides) -> ComplianceReport:
    defaults = dict(
        item_no="1",
        verdicts=[
            RuleVerdict(
                rule_code="R001",
                rule_version=1,
                passed=True,
                explanation="OK",
                placement="carton",
            )
        ],
        applicable_warnings=["Prop 65"],
        passed=True,
    )
    defaults.update(overrides)
    return ComplianceReport(**defaults)


def _make_order_item(state: ItemState = ItemState.CREATED, **kw) -> OrderItem:
    defaults = dict(id="oi-1", order_id="ord-1", item_no="1", state=state)
    defaults.update(kw)
    return OrderItem(**defaults)


# ── Enum tests ─────────────────────────────────────────────────────────────────


class TestItemState:
    def test_has_exactly_12_values(self):
        assert len(ItemState) == 12

    def test_all_members_present(self):
        expected = {
            "CREATED",
            "INTAKE_CLASSIFIED",
            "PARSED",
            "FUSED",
            "COMPLIANCE_EVAL",
            "DRAWING_GENERATED",
            "COMPOSED",
            "VALIDATED",
            "REVIEWED",
            "DELIVERED",
            "HUMAN_BLOCKED",
            "FAILED",
        }
        assert {s.value for s in ItemState} == expected

    def test_string_enum_serialization(self):
        assert ItemState.CREATED.value == "CREATED"
        # .value is the canonical way to get the string; str() varies by Python version
        assert "CREATED" in str(ItemState.CREATED)


class TestDocumentClass:
    def test_has_all_6_values(self):
        assert len(DocumentClass) == 6

    def test_expected_values(self):
        expected = {
            "PURCHASE_ORDER",
            "PROFORMA_INVOICE",
            "PROTOCOL",
            "WARNING_LABELS",
            "CHECKLIST",
            "UNKNOWN",
        }
        assert {d.value for d in DocumentClass} == expected


class TestOrderState:
    def test_has_all_6_values(self):
        assert len(OrderState) == 6


# ── POLineItem tests ──────────────────────────────────────────────────────────


class TestPOLineItem:
    def test_valid_construction(self):
        item = _make_po_line()
        assert item.upc == VALID_UPC
        assert item.confidence == 0.95

    def test_upc_must_be_12_digits(self):
        with pytest.raises(ValidationError):
            _make_po_line(upc="12345")  # too short

    def test_upc_must_be_digits_only(self):
        with pytest.raises(ValidationError):
            _make_po_line(upc="01234567890A")

    def test_upc_luhn_check_digit(self):
        with pytest.raises(ValidationError, match="check digit invalid"):
            _make_po_line(upc="012345678900")  # wrong check digit

    def test_valid_upc_passes_luhn(self):
        item = _make_po_line(upc=VALID_UPC_2)
        assert item.upc == VALID_UPC_2

    def test_total_qty_must_be_positive(self):
        with pytest.raises(ValidationError):
            _make_po_line(total_qty=0)

    def test_net_weight_must_be_positive(self):
        with pytest.raises(ValidationError):
            _make_po_line(net_weight=-1.0)

    def test_confidence_lower_bound(self):
        item = _make_po_line(confidence=0.0)
        assert item.confidence == 0.0

    def test_confidence_upper_bound(self):
        item = _make_po_line(confidence=1.0)
        assert item.confidence == 1.0

    def test_confidence_out_of_range_high(self):
        with pytest.raises(ValidationError):
            _make_po_line(confidence=1.01)

    def test_confidence_out_of_range_low(self):
        with pytest.raises(ValidationError):
            _make_po_line(confidence=-0.01)

    def test_product_image_refs_default_empty(self):
        item = _make_po_line()
        assert item.product_image_refs == []


# ── PILineItem tests ──────────────────────────────────────────────────────────


class TestPILineItem:
    def test_valid_construction(self):
        item = PILineItem(
            item_no="1", box_L=10.0, box_W=8.0, box_H=6.0, total_cartons=5
        )
        assert item.box_L == 10.0

    def test_box_l_must_be_positive(self):
        with pytest.raises(ValidationError):
            PILineItem(
                item_no="1", box_L=0.0, box_W=8.0, box_H=6.0, total_cartons=5
            )

    def test_box_w_must_be_positive(self):
        with pytest.raises(ValidationError):
            PILineItem(
                item_no="1", box_L=10.0, box_W=-1.0, box_H=6.0, total_cartons=5
            )

    def test_box_h_must_be_positive(self):
        with pytest.raises(ValidationError):
            PILineItem(
                item_no="1", box_L=10.0, box_W=8.0, box_H=0.0, total_cartons=5
            )

    def test_total_cartons_must_be_positive(self):
        with pytest.raises(ValidationError):
            PILineItem(
                item_no="1", box_L=10.0, box_W=8.0, box_H=6.0, total_cartons=0
            )

    def test_cbm_must_be_non_negative(self):
        with pytest.raises(ValidationError):
            PILineItem(
                item_no="1",
                box_L=10.0,
                box_W=8.0,
                box_H=6.0,
                total_cartons=5,
                cbm=-0.1,
            )


# ── FusedItem tests ────────────────────────────────────────────────────────────


class TestFusedItem:
    def test_valid_construction(self):
        item = _make_fused_item()
        assert item.confidence == 0.9

    def test_confidence_at_bounds(self):
        assert _make_fused_item(confidence=0.0).confidence == 0.0
        assert _make_fused_item(confidence=1.0).confidence == 1.0

    def test_confidence_out_of_range(self):
        with pytest.raises(ValidationError):
            _make_fused_item(confidence=1.5)

    def test_box_dims_must_be_positive(self):
        with pytest.raises(ValidationError):
            _make_fused_item(box_L=0)
        with pytest.raises(ValidationError):
            _make_fused_item(box_W=-1)
        with pytest.raises(ValidationError):
            _make_fused_item(box_H=0)

    def test_warnings_default_empty(self):
        item = _make_fused_item()
        assert item.warnings == []


# ── FusionResult round-trip serialization ──────────────────────────────────────


class TestFusionResult:
    def test_round_trip_serialization(self):
        fused = _make_fused_item()
        issue = FusionIssue(
            item_no="1",
            field="net_weight",
            severity="warning",
            message="PO and PI differ",
            po_value="2.5",
            pi_value="2.7",
        )
        result = FusionResult(fused_items=[fused], issues=[issue])
        data = result.model_dump()

        # Reconstruct from dict
        restored = FusionResult.model_validate(data)
        assert len(restored.fused_items) == 1
        assert restored.fused_items[0].item_no == "1"
        assert len(restored.issues) == 1
        assert restored.issues[0].severity == "warning"

    def test_json_round_trip(self):
        result = FusionResult(fused_items=[_make_fused_item()])
        json_str = result.model_dump_json()
        restored = FusionResult.model_validate_json(json_str)
        assert restored == result

    def test_issues_default_empty(self):
        result = FusionResult(fused_items=[])
        assert result.issues == []


# ── ComplianceReport tests ─────────────────────────────────────────────────────


class TestComplianceReport:
    def test_structure(self):
        report = _make_compliance_report()
        assert report.passed is True
        assert len(report.verdicts) == 1
        assert report.verdicts[0].rule_code == "R001"
        assert report.applicable_warnings == ["Prop 65"]

    def test_multiple_verdicts(self):
        verdicts = [
            RuleVerdict(
                rule_code=f"R{i:03d}",
                rule_version=1,
                passed=(i % 2 == 0),
                explanation=f"Rule {i}",
                placement="carton",
            )
            for i in range(5)
        ]
        report = ComplianceReport(
            item_no="1",
            verdicts=verdicts,
            applicable_warnings=[],
            passed=False,
        )
        assert len(report.verdicts) == 5
        assert report.passed is False

    def test_rule_verdict_placements(self):
        for placement in ("carton", "product", "both", "hangtag"):
            v = RuleVerdict(
                rule_code="R001",
                rule_version=1,
                passed=True,
                explanation="OK",
                placement=placement,
            )
            assert v.placement == placement


# ── Provenance tests ──────────────────────────────────────────────────────────


class TestProvenance:
    def test_without_llm_snapshot(self):
        p = Provenance(
            artifact_id="art-1",
            artifact_type="svg",
            content_hash="sha256:abc123",
            frozen_inputs=FrozenInputs(),
        )
        assert p.llm_snapshot is None
        assert isinstance(p.created_at, datetime)

    def test_with_llm_snapshot(self):
        snap = LLMSnapshot(model_id="gpt-4", prompt_hash="sha256:xyz")
        p = Provenance(
            artifact_id="art-2",
            artifact_type="pdf",
            content_hash="sha256:def456",
            llm_snapshot=snap,
            frozen_inputs=FrozenInputs(profile_version=3, code_sha="abc"),
        )
        assert p.llm_snapshot.model_id == "gpt-4"
        assert p.llm_snapshot.temperature == 0.0
        assert p.llm_snapshot.max_tokens == 4096
        assert p.frozen_inputs.profile_version == 3

    def test_frozen_inputs_defaults(self):
        fi = FrozenInputs()
        assert fi.profile_version is None
        assert fi.rules_snapshot_id is None
        assert fi.asset_hashes == {}
        assert fi.code_sha is None

    def test_round_trip(self):
        p = Provenance(
            artifact_id="a1",
            artifact_type="svg",
            content_hash="sha256:000",
            frozen_inputs=FrozenInputs(asset_hashes={"logo": "sha256:aaa"}),
        )
        restored = Provenance.model_validate(p.model_dump())
        assert restored.frozen_inputs.asset_hashes["logo"] == "sha256:aaa"


# ── HiTLThread tests ──────────────────────────────────────────────────────────


class TestHiTLThread:
    def test_priorities(self):
        for prio in ("P0", "P1", "P2"):
            t = HiTLThread(
                thread_id="t1",
                order_id="o1",
                item_no="1",
                agent_id="intake",
                priority=prio,
                status="OPEN",
            )
            assert t.priority == prio

    def test_statuses(self):
        for status in ("OPEN", "IN_PROGRESS", "RESOLVED", "ESCALATED"):
            t = HiTLThread(
                thread_id="t1",
                order_id="o1",
                item_no="1",
                agent_id="intake",
                priority="P1",
                status=status,
            )
            assert t.status == status

    def test_created_at_auto_set(self):
        t = HiTLThread(
            thread_id="t1",
            order_id="o1",
            item_no="1",
            agent_id="intake",
            priority="P0",
            status="OPEN",
        )
        assert isinstance(t.created_at, datetime)

    def test_sla_deadline_optional(self):
        t = HiTLThread(
            thread_id="t1",
            order_id="o1",
            item_no="1",
            agent_id="intake",
            priority="P0",
            status="OPEN",
        )
        assert t.sla_deadline is None


class TestHiTLMessage:
    def test_construction(self):
        m = HiTLMessage(
            message_id="m1",
            thread_id="t1",
            sender_type="agent",
            content="Need clarification on item 3",
        )
        assert m.sender_type == "agent"
        assert m.context is None


# ── OrderItem tests ────────────────────────────────────────────────────────────


class TestOrderItem:
    def test_default_state_is_created(self):
        item = _make_order_item()
        assert item.state == ItemState.CREATED

    def test_state_transitions(self):
        """Verify that an OrderItem can be set to every valid ItemState."""
        for state in ItemState:
            item = _make_order_item(state=state)
            assert item.state == state

    def test_state_changed_at_auto_set(self):
        item = _make_order_item()
        assert isinstance(item.state_changed_at, datetime)

    def test_rules_snapshot_id_optional(self):
        item = _make_order_item()
        assert item.rules_snapshot_id is None


# ── compute_order_state tests ──────────────────────────────────────────────────


class TestComputeOrderState:
    def test_failed_yields_attention(self):
        items = [
            _make_order_item(state=ItemState.PARSED),
            _make_order_item(state=ItemState.FAILED, id="oi-2", item_no="2"),
        ]
        assert compute_order_state(items) == OrderState.ATTENTION

    def test_all_delivered(self):
        items = [
            _make_order_item(state=ItemState.DELIVERED, id="oi-1"),
            _make_order_item(state=ItemState.DELIVERED, id="oi-2", item_no="2"),
        ]
        assert compute_order_state(items) == OrderState.DELIVERED

    def test_human_blocked(self):
        items = [
            _make_order_item(state=ItemState.REVIEWED),
            _make_order_item(
                state=ItemState.HUMAN_BLOCKED, id="oi-2", item_no="2"
            ),
        ]
        assert compute_order_state(items) == OrderState.HUMAN_BLOCKED

    def test_ready_to_deliver(self):
        items = [
            _make_order_item(state=ItemState.REVIEWED),
            _make_order_item(state=ItemState.DELIVERED, id="oi-2", item_no="2"),
        ]
        assert compute_order_state(items) == OrderState.READY_TO_DELIVER

    def test_in_progress(self):
        items = [
            _make_order_item(state=ItemState.PARSED),
            _make_order_item(state=ItemState.FUSED, id="oi-2", item_no="2"),
        ]
        assert compute_order_state(items) == OrderState.IN_PROGRESS

    def test_failed_takes_priority_over_human_blocked(self):
        items = [
            _make_order_item(state=ItemState.FAILED),
            _make_order_item(
                state=ItemState.HUMAN_BLOCKED, id="oi-2", item_no="2"
            ),
        ]
        assert compute_order_state(items) == OrderState.ATTENTION


# ── ValidationReport tests ─────────────────────────────────────────────────────


class TestValidationReport:
    def test_all_fields(self):
        report = ValidationReport(
            item_no="1",
            svg_valid=True,
            required_fields_present=True,
            labels_readable=True,
            barcode_scannable=True,
            dimensions_match=True,
            no_overlaps=True,
            passed=True,
        )
        assert report.passed is True
        assert report.issues == []

    def test_with_issues(self):
        report = ValidationReport(
            item_no="1",
            svg_valid=False,
            required_fields_present=True,
            labels_readable=True,
            barcode_scannable=False,
            dimensions_match=True,
            no_overlaps=True,
            passed=False,
            issues=["SVG parse error", "Barcode not scannable"],
        )
        assert len(report.issues) == 2
        assert report.passed is False


# ── DieCutInput composition tests ──────────────────────────────────────────────


class TestDieCutInput:
    def test_composition(self):
        fused = _make_fused_item()
        profile = ImporterProfile(importer_id="imp-1")
        compliance = _make_compliance_report()

        dci = DieCutInput(
            fused_item=fused,
            importer_profile=profile,
            compliance_report=compliance,
            line_drawing_svg="<svg></svg>",
        )
        assert dci.fused_item.item_no == "1"
        assert dci.importer_profile.importer_id == "imp-1"
        assert dci.compliance_report.passed is True
        assert dci.line_drawing_svg == "<svg></svg>"

    def test_line_drawing_svg_optional(self):
        dci = DieCutInput(
            fused_item=_make_fused_item(),
            importer_profile=ImporterProfile(importer_id="imp-1"),
            compliance_report=_make_compliance_report(),
        )
        assert dci.line_drawing_svg is None

    def test_approval_pdf_input(self):
        dci = DieCutInput(
            fused_item=_make_fused_item(),
            importer_profile=ImporterProfile(importer_id="imp-1"),
            compliance_report=_make_compliance_report(),
        )
        pdf_input = ApprovalPDFInput(order_id="ord-1", items=[dci])
        assert pdf_input.order_id == "ord-1"
        assert len(pdf_input.items) == 1


# ── ImporterProfile tests ─────────────────────────────────────────────────────


class TestImporterProfile:
    def test_defaults(self):
        p = ImporterProfile(importer_id="imp-1")
        assert p.version == 1
        assert p.brand_treatment is None
        assert p.logo_asset_hash is None

    def test_with_all_fields(self):
        p = ImporterProfile(
            importer_id="imp-2",
            brand_treatment={"color": "blue"},
            panel_layouts={"front": "A"},
            handling_symbol_rules={"fragile": True},
            pi_template_mapping={"col_a": "box_L"},
            logo_asset_hash="sha256:logo",
            version=3,
        )
        assert p.version == 3
        assert p.brand_treatment["color"] == "blue"
