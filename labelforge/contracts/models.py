"""Pydantic v2 contract models for the Labelforge export-labeling-automation pipeline."""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator


# ── Enums ──────────────────────────────────────────────────────────────────────


class ItemState(str, Enum):
    CREATED = "CREATED"
    INTAKE_CLASSIFIED = "INTAKE_CLASSIFIED"
    PARSED = "PARSED"
    FUSED = "FUSED"
    COMPLIANCE_EVAL = "COMPLIANCE_EVAL"
    DRAWING_GENERATED = "DRAWING_GENERATED"
    COMPOSED = "COMPOSED"
    VALIDATED = "VALIDATED"
    REVIEWED = "REVIEWED"
    DELIVERED = "DELIVERED"
    HUMAN_BLOCKED = "HUMAN_BLOCKED"
    FAILED = "FAILED"


class DocumentClass(str, Enum):
    PURCHASE_ORDER = "PURCHASE_ORDER"
    PROFORMA_INVOICE = "PROFORMA_INVOICE"
    PROTOCOL = "PROTOCOL"
    WARNING_LABELS = "WARNING_LABELS"
    CHECKLIST = "CHECKLIST"
    UNKNOWN = "UNKNOWN"


class OrderState(str, Enum):
    CREATED = "CREATED"
    IN_PROGRESS = "IN_PROGRESS"
    HUMAN_BLOCKED = "HUMAN_BLOCKED"
    ATTENTION = "ATTENTION"
    READY_TO_DELIVER = "READY_TO_DELIVER"
    DELIVERED = "DELIVERED"


# ── Line-item models ──────────────────────────────────────────────────────────


class POLineItem(BaseModel):
    model_config = ConfigDict(json_schema_extra={"example": {
        "item_no": "1",
        "upc": "012345678905",
        "gtin": None,
        "description": "Ceramic Mug 11oz",
        "product_dims": {"length": 4.5, "width": 3.5, "height": 4.0, "unit": "in"},
        "net_weight": 0.75,
        "case_qty": "24",
        "total_qty": 480,
        "product_image_refs": ["s3://assets/mug-11oz-front.jpg"],
        "confidence": 0.95,
    }})

    item_no: str
    upc: str = Field(..., min_length=12, max_length=12)
    gtin: Optional[str] = None
    description: str
    product_dims: Optional[dict] = None
    net_weight: Optional[float] = Field(None, gt=0)
    case_qty: str
    total_qty: int = Field(..., gt=0)
    product_image_refs: list[str] = Field(default_factory=list)
    confidence: float = Field(..., ge=0, le=1)

    @field_validator("upc")
    @classmethod
    def validate_upc_digits(cls, v: str) -> str:
        if not v.isdigit():
            raise ValueError("UPC must contain only digits")
        return v

    @field_validator("upc")
    @classmethod
    def validate_upc_luhn(cls, v: str) -> str:
        """Validate UPC check digit using Luhn-like algorithm."""
        digits = [int(d) for d in v]
        odd_sum = sum(digits[i] for i in range(0, 11, 2))
        even_sum = sum(digits[i] for i in range(1, 11, 2))
        check = (10 - (odd_sum * 3 + even_sum) % 10) % 10
        if check != digits[11]:
            raise ValueError(
                f"UPC check digit invalid: expected {check}, got {digits[11]}"
            )
        return v


class PILineItem(BaseModel):
    model_config = ConfigDict(json_schema_extra={"example": {
        "item_no": "1",
        "box_L": 12.5,
        "box_W": 10.0,
        "box_H": 8.5,
        "cbm": 0.0106,
        "total_cartons": 20,
        "inner_pack": 4,
        "hs_code": "6912.00",
    }})

    item_no: str
    box_L: float = Field(..., gt=0)
    box_W: float = Field(..., gt=0)
    box_H: float = Field(..., gt=0)
    cbm: Optional[float] = Field(None, ge=0)
    total_cartons: int = Field(..., gt=0)
    inner_pack: Optional[int] = None
    hs_code: Optional[str] = None


# ── Fusion models ──────────────────────────────────────────────────────────────


class FusedItem(BaseModel):
    model_config = ConfigDict(json_schema_extra={"example": {
        "item_no": "1",
        "upc": "012345678905",
        "description": "Ceramic Mug 11oz",
        "case_qty": "24",
        "box_L": 12.5,
        "box_W": 10.0,
        "box_H": 8.5,
        "product_dims": {"length": 4.5, "width": 3.5, "height": 4.0, "unit": "in"},
        "net_weight": 0.75,
        "total_qty": 480,
        "total_cartons": 20,
        "material": "Stoneware ceramic",
        "finish": "Glossy glaze",
        "warnings": ["FRAGILE", "THIS SIDE UP"],
        "confidence": 0.93,
    }})

    item_no: str
    upc: str
    description: str
    case_qty: str
    box_L: float = Field(..., gt=0)
    box_W: float = Field(..., gt=0)
    box_H: float = Field(..., gt=0)
    product_dims: Optional[dict] = None
    net_weight: Optional[float] = None
    total_qty: int = Field(..., gt=0)
    total_cartons: int = Field(..., gt=0)
    material: Optional[str] = None
    finish: Optional[str] = None
    warnings: list[str] = Field(default_factory=list)
    confidence: float = Field(..., ge=0, le=1)


class FusionIssue(BaseModel):
    model_config = ConfigDict(json_schema_extra={"example": {
        "item_no": "1",
        "field": "net_weight",
        "severity": "warning",
        "message": "Net weight on PO (0.75 kg) differs from PI (0.80 kg) by >5%",
        "po_value": "0.75",
        "pi_value": "0.80",
    }})

    item_no: str
    field: str
    severity: str  # "critical", "warning", "info"
    message: str
    po_value: Optional[str] = None
    pi_value: Optional[str] = None


class FusionResult(BaseModel):
    model_config = ConfigDict(json_schema_extra={"example": {
        "fused_items": [{
            "item_no": "1", "upc": "012345678905",
            "description": "Ceramic Mug 11oz", "case_qty": "24",
            "box_L": 12.5, "box_W": 10.0, "box_H": 8.5,
            "net_weight": 0.75, "total_qty": 480, "total_cartons": 20,
            "material": "Stoneware ceramic", "finish": "Glossy glaze",
            "warnings": ["FRAGILE"], "confidence": 0.93,
        }],
        "issues": [{
            "item_no": "1", "field": "net_weight", "severity": "warning",
            "message": "Net weight on PO (0.75 kg) differs from PI (0.80 kg) by >5%",
            "po_value": "0.75", "pi_value": "0.80",
        }],
    }})

    fused_items: list[FusedItem]
    issues: list[FusionIssue] = Field(default_factory=list)


# ── Compliance models ─────────────────────────────────────────────────────────


class RuleVerdict(BaseModel):
    model_config = ConfigDict(json_schema_extra={"example": {
        "rule_code": "PROP65_CERAMIC",
        "rule_version": 3,
        "passed": True,
        "explanation": "Prop 65 warning required for ceramic products sold in California; label present.",
        "placement": "product",
    }})

    rule_code: str
    rule_version: int
    passed: bool
    explanation: str
    placement: str  # "carton", "product", "both", "hangtag"


class ComplianceReport(BaseModel):
    model_config = ConfigDict(json_schema_extra={"example": {
        "item_no": "1",
        "verdicts": [{
            "rule_code": "PROP65_CERAMIC", "rule_version": 3, "passed": True,
            "explanation": "Prop 65 warning required for ceramic products sold in California; label present.",
            "placement": "product",
        }],
        "applicable_warnings": ["California Proposition 65 – lead and cadmium in ceramic glaze"],
        "passed": True,
    }})

    item_no: str
    verdicts: list[RuleVerdict]
    applicable_warnings: list[str]
    passed: bool


# ── Provenance models ─────────────────────────────────────────────────────────


class LLMSnapshot(BaseModel):
    model_config = ConfigDict(json_schema_extra={"example": {
        "model_id": "gpt-5.4",
        "prompt_hash": "sha256:a3f1c9b2e8d74506f1234567890abcdef1234567",
        "temperature": 0.0,
        "max_tokens": 4096,
    }})

    model_id: str
    prompt_hash: str
    temperature: float = 0.0
    max_tokens: int = 4096


class FrozenInputs(BaseModel):
    model_config = ConfigDict(json_schema_extra={"example": {
        "profile_version": 2,
        "rules_snapshot_id": "rules-2026-03-15-v4",
        "asset_hashes": {
            "logo.svg": "sha256:b4d3f1a2c5e6789012345abcdef67890",
            "fragile_symbol.svg": "sha256:c8e2a1f3d4567890abcdef1234567890",
        },
        "code_sha": "abc1234def5678",
    }})

    profile_version: Optional[int] = None
    rules_snapshot_id: Optional[str] = None
    asset_hashes: dict[str, str] = Field(default_factory=dict)
    code_sha: Optional[str] = None


class Provenance(BaseModel):
    model_config = ConfigDict(json_schema_extra={"example": {
        "artifact_id": "diecut-item1-v3",
        "artifact_type": "die_cut_svg",
        "content_hash": "sha256:e7f8a9b0c1d2e3f4567890abcdef1234",
        "llm_snapshot": {
            "model_id": "gpt-5.4",
            "prompt_hash": "sha256:a3f1c9b2e8d74506f1234567890abcdef1234567",
            "temperature": 0.0,
            "max_tokens": 4096,
        },
        "frozen_inputs": {
            "profile_version": 2,
            "rules_snapshot_id": "rules-2026-03-15-v4",
            "asset_hashes": {"logo.svg": "sha256:b4d3f1a2c5e6789012345abcdef67890"},
            "code_sha": "abc1234def5678",
        },
        "created_at": "2026-04-12T10:30:00Z",
    }})

    artifact_id: str
    artifact_type: str
    content_hash: str
    llm_snapshot: Optional[LLMSnapshot] = None
    frozen_inputs: FrozenInputs
    created_at: datetime = Field(default_factory=datetime.utcnow)


# ── Importer / drawing models ─────────────────────────────────────────────────


class ImporterProfile(BaseModel):
    model_config = ConfigDict(json_schema_extra={"example": {
        "importer_id": "IMP-ACME-001",
        "brand_treatment": {
            "company_name": "Acme Trading Co",
            "font": "Helvetica Neue",
            "primary_color": "#1A3C6E",
        },
        "panel_layouts": {"carton_5_panel": "template-5p-v2"},
        "handling_symbol_rules": {
            "fragile": True,
            "this_side_up": True,
            "keep_dry": False,
        },
        "pi_template_mapping": {"default": "acme-pi-template-v3"},
        "logo_asset_hash": "sha256:f1e2d3c4b5a6978800112233aabbccdd",
        "version": 2,
    }})

    importer_id: str
    name: Optional[str] = None
    code: Optional[str] = None
    brand_treatment: Optional[dict] = None
    panel_layouts: Optional[dict] = None
    handling_symbol_rules: Optional[dict] = None
    pi_template_mapping: Optional[dict] = None
    logo_asset_hash: Optional[str] = None
    version: int = 1


class DieCutInput(BaseModel):
    model_config = ConfigDict(json_schema_extra={"example": {
        "fused_item": {
            "item_no": "1", "upc": "012345678905",
            "description": "Ceramic Mug 11oz", "case_qty": "24",
            "box_L": 12.5, "box_W": 10.0, "box_H": 8.5,
            "net_weight": 0.75, "total_qty": 480, "total_cartons": 20,
            "material": "Stoneware ceramic", "warnings": ["FRAGILE"],
            "confidence": 0.93,
        },
        "importer_profile": {
            "importer_id": "IMP-ACME-001",
            "handling_symbol_rules": {"fragile": True, "this_side_up": True},
            "version": 2,
        },
        "compliance_report": {
            "item_no": "1",
            "verdicts": [{"rule_code": "PROP65_CERAMIC", "rule_version": 3,
                          "passed": True, "explanation": "Prop 65 label present.",
                          "placement": "product"}],
            "applicable_warnings": ["California Proposition 65"],
            "passed": True,
        },
        "line_drawing_svg": "<svg>...</svg>",
    }})

    fused_item: FusedItem
    importer_profile: ImporterProfile
    compliance_report: ComplianceReport
    line_drawing_svg: Optional[str] = None


class ApprovalPDFInput(BaseModel):
    model_config = ConfigDict(json_schema_extra={"example": {
        "order_id": "ORD-2026-04-0042",
        "items": [{
            "fused_item": {
                "item_no": "1", "upc": "012345678905",
                "description": "Ceramic Mug 11oz", "case_qty": "24",
                "box_L": 12.5, "box_W": 10.0, "box_H": 8.5,
                "total_qty": 480, "total_cartons": 20,
                "warnings": ["FRAGILE"], "confidence": 0.93,
            },
            "importer_profile": {"importer_id": "IMP-ACME-001", "version": 2},
            "compliance_report": {
                "item_no": "1", "verdicts": [], "applicable_warnings": [],
                "passed": True,
            },
        }],
    }})

    order_id: str
    items: list[DieCutInput]


# ── Validation models ─────────────────────────────────────────────────────────


class ValidationReport(BaseModel):
    model_config = ConfigDict(json_schema_extra={"example": {
        "item_no": "1",
        "svg_valid": True,
        "required_fields_present": True,
        "labels_readable": True,
        "barcode_scannable": True,
        "dimensions_match": True,
        "no_overlaps": True,
        "passed": True,
        "issues": [],
    }})

    item_no: str
    svg_valid: bool
    required_fields_present: bool
    labels_readable: bool
    barcode_scannable: bool
    dimensions_match: bool
    no_overlaps: bool
    passed: bool
    issues: list[str] = Field(default_factory=list)


# ── Human-in-the-loop models ──────────────────────────────────────────────────


class HiTLThread(BaseModel):
    model_config = ConfigDict(json_schema_extra={"example": {
        "thread_id": "HITL-20260412-001",
        "order_id": "ORD-2026-04-0042",
        "item_no": "1",
        "agent_id": "fusion-agent",
        "priority": "P1",
        "status": "OPEN",
        "sla_deadline": "2026-04-12T18:00:00Z",
        "created_at": "2026-04-12T10:30:00Z",
    }})

    thread_id: str
    order_id: str
    item_no: str
    agent_id: str
    priority: str  # "P0", "P1", "P2"
    status: str  # "OPEN", "IN_PROGRESS", "RESOLVED", "ESCALATED"
    sla_deadline: Optional[datetime] = None
    created_at: datetime = Field(default_factory=datetime.utcnow)


class HiTLMessage(BaseModel):
    model_config = ConfigDict(json_schema_extra={"example": {
        "message_id": "MSG-20260412-001",
        "thread_id": "HITL-20260412-001",
        "sender_type": "agent",
        "content": "Net weight mismatch between PO (0.75 kg) and PI (0.80 kg) for item 1. Please confirm the correct value.",
        "context": {"po_weight": 0.75, "pi_weight": 0.80, "delta_pct": 6.7},
        "created_at": "2026-04-12T10:30:00Z",
    }})

    message_id: str
    thread_id: str
    sender_type: str  # "agent", "human"
    content: str
    context: Optional[dict] = None
    created_at: datetime = Field(default_factory=datetime.utcnow)


# ── Order tracking ─────────────────────────────────────────────────────────────


class OrderItem(BaseModel):
    model_config = ConfigDict(json_schema_extra={"example": {
        "id": "OI-20260412-001",
        "order_id": "ORD-2026-04-0042",
        "item_no": "1",
        "state": "PARSED",
        "state_changed_at": "2026-04-12T10:45:00Z",
        "rules_snapshot_id": "rules-2026-03-15-v4",
    }})

    id: str
    order_id: str
    item_no: str
    state: ItemState = ItemState.CREATED
    state_changed_at: datetime = Field(default_factory=datetime.utcnow)
    rules_snapshot_id: Optional[str] = None
    data: Optional[dict] = None


# ── Order-state derivation ─────────────────────────────────────────────────────

STAGE_ORDER = {s: i for i, s in enumerate(ItemState)}


def compute_order_state(items: list[OrderItem]) -> OrderState:
    """Derive the aggregate order state from its constituent items."""
    if any(i.state == ItemState.FAILED for i in items):
        return OrderState.ATTENTION
    if all(i.state == ItemState.DELIVERED for i in items):
        return OrderState.DELIVERED
    if any(i.state == ItemState.HUMAN_BLOCKED for i in items):
        return OrderState.HUMAN_BLOCKED
    if all(i.state in {ItemState.REVIEWED, ItemState.DELIVERED} for i in items):
        return OrderState.READY_TO_DELIVER
    return OrderState.IN_PROGRESS
