"""Registry of per-agent HITL chat handlers.

Each agent that can pause to HITL gets a handler here. Handlers are
registered under every ``agent_id`` value that might show up on a thread
row — which, for historical reasons, is three different namespaces:

* **Advance-pipeline activities** (``compliance_eval_activity`` etc.) —
  these are the values written by :func:`_ensure_hitl_thread` in
  ``labelforge/api/v1/orders.py``, and are what production threads
  actually look like today.
* **UI catalogue ids** (``composer_agent`` etc.) — from
  :data:`labelforge.agents.registry.AGENT_CATALOGUE`. These show up on
  threads created via the ``POST /hitl/threads`` endpoint when an
  external caller (or a future agent-library refactor) uses the
  canonical short name.
* **Seed-data names** (``compliance-agent`` etc.) — only in the dev-seed
  rows. Kept here so local demos don't land in the fallback path.

The idea is: one behavioural handler per *kind* of agent, aliased under
every id it might wear.
"""
from __future__ import annotations

from labelforge.agents.chat import (
    GenericChatHandler,
    register_chat_handler,
)


# ── Patch allowlists per agent ──────────────────────────────────────────────
#
# These mirror what each activity actually reads from item.data. Keeping
# the lists narrow is a deliberate safety tradeoff — operators who need a
# field that isn't on the allowlist will see "I tried to update fields
# I'm not authorized to change..." and can edit the field manually.

_FUSION_PATCH_KEYS = (
    "item_no", "upc", "description", "case_qty", "total_qty",
    "total_cartons", "box_L", "box_W", "box_H",
    "net_weight", "gross_weight_lbs", "cube_cuft",
    "country_of_origin", "importer_id",
    "carton_count", "confidence",
)

_COMPLIANCE_PATCH_KEYS = (
    "applicable_warnings", "handling_symbols",
    "country_of_origin", "destination_region",
    "hazard_class", "age_grade",
)

_COMPOSER_PATCH_KEYS = (
    # The composer is template-driven; structural layout cannot be
    # edited via chat. What CAN change is the inputs it reads from:
    "line_drawing_svg", "importer_profile_overrides",
)

_VALIDATOR_PATCH_KEYS = (
    # Validator re-runs after data is corrected — allow the same fields
    # fusion can touch plus the compliance ones.
    *_FUSION_PATCH_KEYS,
    *_COMPLIANCE_PATCH_KEYS,
)

_INTAKE_PATCH_KEYS = (
    "doc_class", "classification_confidence",
    "document_type", "language",
)

_PROTOCOL_PATCH_KEYS = (
    "protocol_version", "required_fields",
)

_PO_PARSER_PATCH_KEYS = (
    "po_number", "po_date", "buyer_id", "ship_to", "incoterms",
    "currency", "items",
)

_WARNING_LABEL_PATCH_KEYS = (
    "applicable_warnings", "regional_warnings",
)

_CHECKLIST_PATCH_KEYS = (
    "checklist_items", "required_documents",
)

_PRODUCT_IMAGE_PATCH_KEYS = (
    "product_image_url", "product_image_hash", "image_notes",
)

_DRAWING_PATCH_KEYS = (
    "line_drawing_svg", "drawing_notes",
)


# ── Handler bank ────────────────────────────────────────────────────────────
#
# The tuple is (canonical_agent_id_list, role_description, patch_keys).
# Every id in the list registers under the same handler instance.

_HANDLERS: tuple[tuple[tuple[str, ...], str, tuple[str, ...]], ...] = (
    # ── Fusion ────────────────────────────────────────────────────────
    (
        ("fusion_agent", "fusion-agent", "fuse_items_activity", "fusion"),
        "the Fusion Agent — you merge PO, PI, and product-image data into "
        "a single authoritative fused item record. You pause when the "
        "source documents disagree or a required field is missing.",
        _FUSION_PATCH_KEYS,
    ),
    # ── Compliance ───────────────────────────────────────────────────
    (
        (
            "compliance_classifier", "compliance-agent", "compliance_eval_activity",
            "rule_evaluator",
        ),
        "the Compliance Classifier — you evaluate rules against the fused "
        "item (Prop 65, FDA, CPSC, regional warnings) and decide which "
        "warning labels must appear. You pause when a rule's inputs are "
        "ambiguous (e.g. the destination region or hazard class is unclear). "
        "Prefer tools over asking the operator: `list_compliance_rules` "
        "returns the full rule logic for this tenant, "
        "`get_onboarding_extraction(agent=\"checklist\")` shows the rules "
        "the checklist agent extracted, and `search_documents(query=...)` "
        "finds the source protocol document by keyword.",
        _COMPLIANCE_PATCH_KEYS,
    ),
    # ── Composer ─────────────────────────────────────────────────────
    (
        ("composer_agent", "compose_label_activity", "composer"),
        "the Composer Agent — you generate the die-cut SVG from the fused "
        "item + importer profile + compliance report. You pause when a "
        "required input is missing or the importer profile references a "
        "template field you can't render. NOTE: you are template-driven, "
        "not LLM-driven, so you cannot 'redesign' a label during chat — "
        "you can only ask the operator to supply the missing input and "
        "then re-run. Useful tools: `get_importer_profile` (full panel "
        "layouts + brand treatment) and `get_item_data(item_no=...)` "
        "for sibling items on the same order.",
        _COMPOSER_PATCH_KEYS,
    ),
    # ── Validator ────────────────────────────────────────────────────
    (
        ("validator_agent", "validation-agent", "validate_output_activity", "validator"),
        "the Validator Agent — you check the composed die-cut SVG against "
        "the rules registry and the importer profile. You pause when a "
        "validation failure can't be auto-fixed. Your job during chat is "
        "to explain exactly which rule failed and help the operator "
        "decide whether to (a) patch the item data and re-run, (b) accept "
        "the failure with an override note, or (c) escalate. Tools: "
        "`list_compliance_rules` for the rule that failed, "
        "`list_warning_labels` for label text, `get_item_data` for a "
        "sibling that passed.",
        _VALIDATOR_PATCH_KEYS,
    ),
    # ── Intake / classification ───────────────────────────────────────
    (
        ("intake_classifier", "intake_classify_activity"),
        "the Intake Classifier — you classify uploaded documents (PO, PI, "
        "product image, warning-label sheet) by type + language. You pause "
        "when the document doesn't match any known class with high "
        "confidence.",
        _INTAKE_PATCH_KEYS,
    ),
    (
        ("protocol_analyzer",),
        "the Protocol Analyzer — you detect which importer / export "
        "protocol applies to an order and which required fields must be "
        "populated. You pause when the protocol can't be determined from "
        "the ingested documents.",
        _PROTOCOL_PATCH_KEYS,
    ),
    (
        ("po_parser", "pi_parser"),
        "a document parser (PO or PI) — you extract structured line items "
        "and metadata from a supplier document. You pause when a field is "
        "present in the document but you can't parse it confidently.",
        _PO_PARSER_PATCH_KEYS,
    ),
    (
        ("warning_label_parser",),
        "the Warning Label Parser — you extract the list of applicable "
        "warnings (FDA, Prop 65, CPSC, etc.) from a warning-label sheet. "
        "You pause when the sheet is ambiguous about regional applicability.",
        _WARNING_LABEL_PATCH_KEYS,
    ),
    (
        ("checklist_extractor",),
        "the Checklist Extractor — you extract the importer-specific "
        "compliance checklist from a reference document. You pause when "
        "an item on the checklist needs human interpretation.",
        _CHECKLIST_PATCH_KEYS,
    ),
    (
        ("product_image_processor",),
        "the Product Image Processor — you normalize and tag product "
        "photos so they can be inserted into a die-cut. You pause when "
        "the image is unusable (wrong angle, watermark, missing).",
        _PRODUCT_IMAGE_PATCH_KEYS,
    ),
    (
        ("generate_drawing_activity", "artifact_generator", "drawing_generator"),
        "the Line-Drawing Generator — you synthesize a simple line drawing "
        "of the item for the die-cut. You pause when the source photo "
        "doesn't give enough detail or the importer profile demands a "
        "drawing style you can't produce.",
        _DRAWING_PATCH_KEYS,
    ),
    # ── Output + orchestration (chat-only, no patches) ───────────────
    (
        ("bundle_assembler",),
        "the Bundle Assembler — you stitch composed die-cuts into a "
        "single approval-ready PDF. You only pause on infrastructure "
        "errors (missing artifact, corrupted blob).",
        (),
    ),
    (
        ("notification_dispatcher",),
        "the Notification Dispatcher — you deliver approval emails + "
        "Slack messages once an order is REVIEWED. You only pause on "
        "delivery failures.",
        (),
    ),
    (
        ("order_processor",),
        "the Order Processor — the top-level workflow orchestrator. You "
        "pause when an upstream stage surfaces a non-retryable error.",
        (),
    ),
    (
        ("provenance_tracker",),
        "the Provenance Tracker — you record which inputs produced which "
        "artifacts. You pause when a required provenance field is missing.",
        (),
    ),
    (
        ("cost_breaker",),
        "the Cost Breaker — a guardrail that pauses the pipeline when a "
        "tenant is over budget. Human decision: authorize the spend or "
        "hold the order.",
        (),
    ),
    (
        ("hitl_resolver",),
        "the HITL Resolver — the utility agent that consolidates "
        "multi-stage blocks into a single review. You pause to request "
        "a summary decision from the operator.",
        (),
    ),
)


def _register_all() -> None:
    """Register one handler per (canonical_id, ...alias) tuple."""
    for ids, role, patches in _HANDLERS:
        canonical = ids[0]
        handler = GenericChatHandler(
            agent_id=canonical,
            role_description=role,
            patch_allowlist=patches,
        )
        for agent_id in ids:
            # Each alias points at the same handler instance; agent_id on
            # the handler itself stays canonical for prompt readability.
            aliased = GenericChatHandler(
                agent_id=agent_id,
                role_description=role,
                patch_allowlist=patches,
            )
            register_chat_handler(aliased)


# Register on import so any module that depends on chat.get_chat_handler
# just works. Safe to call multiple times — register_chat_handler
# overwrites.
_register_all()


__all__ = ["_register_all"]
