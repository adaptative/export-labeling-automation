"""Pydantic v2 contract models for the Labelforge export-labeling-automation pipeline."""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field, field_validator


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
    item_no: str
    field: str
    severity: str  # "critical", "warning", "info"
    message: str
    po_value: Optional[str] = None
    pi_value: Optional[str] = None


class FusionResult(BaseModel):
    fused_items: list[FusedItem]
    issues: list[FusionIssue] = Field(default_factory=list)


# ── Compliance models ─────────────────────────────────────────────────────────


class RuleVerdict(BaseModel):
    rule_code: str
    rule_version: int
    passed: bool
    explanation: str
    placement: str  # "carton", "product", "both", "hangtag"


class ComplianceReport(BaseModel):
    item_no: str
    verdicts: list[RuleVerdict]
    applicable_warnings: list[str]
    passed: bool


# ── Provenance models ─────────────────────────────────────────────────────────


class LLMSnapshot(BaseModel):
    model_id: str
    prompt_hash: str
    temperature: float = 0.0
    max_tokens: int = 4096


class FrozenInputs(BaseModel):
    profile_version: Optional[int] = None
    rules_snapshot_id: Optional[str] = None
    asset_hashes: dict[str, str] = Field(default_factory=dict)
    code_sha: Optional[str] = None


class Provenance(BaseModel):
    artifact_id: str
    artifact_type: str
    content_hash: str
    llm_snapshot: Optional[LLMSnapshot] = None
    frozen_inputs: FrozenInputs
    created_at: datetime = Field(default_factory=datetime.utcnow)


# ── Importer / drawing models ─────────────────────────────────────────────────


class ImporterProfile(BaseModel):
    importer_id: str
    brand_treatment: Optional[dict] = None
    panel_layouts: Optional[dict] = None
    handling_symbol_rules: Optional[dict] = None
    pi_template_mapping: Optional[dict] = None
    logo_asset_hash: Optional[str] = None
    version: int = 1


class DieCutInput(BaseModel):
    fused_item: FusedItem
    importer_profile: ImporterProfile
    compliance_report: ComplianceReport
    line_drawing_svg: Optional[str] = None


class ApprovalPDFInput(BaseModel):
    order_id: str
    items: list[DieCutInput]


# ── Validation models ─────────────────────────────────────────────────────────


class ValidationReport(BaseModel):
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
    thread_id: str
    order_id: str
    item_no: str
    agent_id: str
    priority: str  # "P0", "P1", "P2"
    status: str  # "OPEN", "IN_PROGRESS", "RESOLVED", "ESCALATED"
    sla_deadline: Optional[datetime] = None
    created_at: datetime = Field(default_factory=datetime.utcnow)


class HiTLMessage(BaseModel):
    message_id: str
    thread_id: str
    sender_type: str  # "agent", "human"
    content: str
    context: Optional[dict] = None
    created_at: datetime = Field(default_factory=datetime.utcnow)


# ── Order tracking ─────────────────────────────────────────────────────────────


class OrderItem(BaseModel):
    id: str
    order_id: str
    item_no: str
    state: ItemState = ItemState.CREATED
    state_changed_at: datetime = Field(default_factory=datetime.utcnow)
    rules_snapshot_id: Optional[str] = None


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
