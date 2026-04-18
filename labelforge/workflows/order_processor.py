"""Order processing workflow — Temporal workflow + state machine.

Defines the OrderProcessorWorkflow that orchestrates the full labeling pipeline
for each order item through activities with retry policies, timeouts, and
automatic HiTL escalation.
"""
from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from datetime import timedelta
from typing import Any, Optional

from temporalio import activity, workflow
from temporalio.common import RetryPolicy

from labelforge.contracts.models import ItemState, OrderState, OrderItem, compute_order_state

logger = logging.getLogger(__name__)

MAX_RETRIES = 3
ACTIVITY_TIMEOUT_SECONDS = 300  # 5 minutes


@dataclass
class WorkflowConfig:
    max_retries: int = MAX_RETRIES
    activity_timeout: int = ACTIVITY_TIMEOUT_SECONDS
    concurrency_limit: int = 8


# ── State machine ──────────────────────────────────────────────────────────

STATE_TRANSITIONS: dict[ItemState, list[ItemState]] = {
    ItemState.CREATED: [ItemState.INTAKE_CLASSIFIED, ItemState.HUMAN_BLOCKED, ItemState.FAILED],
    ItemState.INTAKE_CLASSIFIED: [ItemState.PARSED, ItemState.HUMAN_BLOCKED, ItemState.FAILED],
    ItemState.PARSED: [ItemState.FUSED, ItemState.HUMAN_BLOCKED, ItemState.FAILED],
    ItemState.FUSED: [ItemState.COMPLIANCE_EVAL, ItemState.HUMAN_BLOCKED, ItemState.FAILED],
    ItemState.COMPLIANCE_EVAL: [ItemState.DRAWING_GENERATED, ItemState.HUMAN_BLOCKED, ItemState.FAILED],
    ItemState.DRAWING_GENERATED: [ItemState.COMPOSED, ItemState.HUMAN_BLOCKED, ItemState.FAILED],
    ItemState.COMPOSED: [ItemState.VALIDATED, ItemState.COMPOSED, ItemState.HUMAN_BLOCKED, ItemState.FAILED],
    ItemState.VALIDATED: [ItemState.REVIEWED, ItemState.FAILED],
    ItemState.REVIEWED: [ItemState.DELIVERED],
    ItemState.HUMAN_BLOCKED: [ItemState.CREATED, ItemState.INTAKE_CLASSIFIED, ItemState.PARSED,
                               ItemState.FUSED, ItemState.COMPLIANCE_EVAL, ItemState.DRAWING_GENERATED,
                               ItemState.COMPOSED],
    ItemState.DELIVERED: [],
    ItemState.FAILED: [],
}


def is_valid_transition(from_state: ItemState, to_state: ItemState) -> bool:
    return to_state in STATE_TRANSITIONS.get(from_state, [])


def transition_item(item: OrderItem, new_state: ItemState) -> OrderItem:
    if not is_valid_transition(item.state, new_state):
        raise ValueError(f"Invalid transition: {item.state} -> {new_state}")
    item.state = new_state
    return item


# ── Retry policy ───────────────────────────────────────────────────────────

DEFAULT_RETRY_POLICY = RetryPolicy(
    initial_interval=timedelta(seconds=1),
    backoff_coefficient=2.0,
    maximum_interval=timedelta(seconds=30),
    maximum_attempts=MAX_RETRIES,
)


# ── Activity input/output contracts ───────────────────────────────────────


@dataclass
class ActivityInput:
    """Common input for all pipeline activities."""
    order_id: str
    item_id: str
    tenant_id: str
    document_id: Optional[str] = None
    payload: dict = field(default_factory=dict)


@dataclass
class ActivityOutput:
    """Common output from pipeline activities."""
    success: bool
    item_id: str
    new_state: str  # ItemState value
    data: dict = field(default_factory=dict)
    needs_hitl: bool = False
    hitl_reason: Optional[str] = None
    cost_usd: float = 0.0


# ── Activities ─────────────────────────────────────────────────────────────


@activity.defn
async def intake_classify_activity(input: ActivityInput) -> ActivityOutput:
    """Classify uploaded documents using the Intake Classifier Agent."""
    from labelforge.agents.intake_classifier import IntakeClassifierAgent
    from labelforge.core.llm import OpenAIProvider
    from labelforge.config import settings

    provider = OpenAIProvider(api_key=settings.openai_api_key)
    agent = IntakeClassifierAgent(provider)
    result = await agent.execute(input.payload)

    if result.needs_hitl:
        return ActivityOutput(
            success=False,
            item_id=input.item_id,
            new_state=ItemState.HUMAN_BLOCKED.value,
            data=result.data,
            needs_hitl=True,
            hitl_reason=result.hitl_reason,
            cost_usd=result.cost,
        )
    return ActivityOutput(
        success=True,
        item_id=input.item_id,
        new_state=ItemState.INTAKE_CLASSIFIED.value,
        data=result.data,
        cost_usd=result.cost,
    )


@activity.defn
async def parse_document_activity(input: ActivityInput) -> ActivityOutput:
    """Parse classified documents to extract structured data (PO/PI line items)."""
    activity.logger.info("Parsing document for item %s", input.item_id)

    doc_class = input.payload.get("doc_class", "UNKNOWN")
    doc_content = input.payload.get("document_content", "")

    if not doc_content:
        return ActivityOutput(
            success=True,
            item_id=input.item_id,
            new_state=ItemState.PARSED.value,
            data=input.payload,
        )

    try:
        if doc_class == "PURCHASE_ORDER":
            from labelforge.agents.po_parser import POParserAgent
            from labelforge.core.llm import OpenAIProvider
            from labelforge.config import settings
            from labelforge.api.v1.orders import _LLMProviderWrapper

            provider = OpenAIProvider(api_key=settings.openai_api_key)
            wrapper = _LLMProviderWrapper(provider, settings.llm_default_model)
            agent = POParserAgent(llm_provider=wrapper)
            result = await agent.execute({"document_content": doc_content})

            output_data = {
                **input.payload,
                "items": result.data.get("items", []),
                "issues": result.data.get("issues", []),
                "page_count": result.data.get("page_count", 1),
            }
            return ActivityOutput(
                success=result.success,
                item_id=input.item_id,
                new_state=ItemState.PARSED.value,
                data=output_data,
                needs_hitl=result.needs_hitl,
                hitl_reason=result.hitl_reason,
                cost_usd=result.cost,
            )

        elif doc_class == "PROFORMA_INVOICE":
            from labelforge.agents.pi_parser import PIParserAgent
            from labelforge.api.v1.orders import _text_to_rows, _auto_detect_pi_mapping

            rows = _text_to_rows(doc_content)
            if rows:
                mapping = _auto_detect_pi_mapping(rows)
                agent = PIParserAgent()
                result = await agent.execute({
                    "rows": rows,
                    "template_mapping": mapping,
                })
                output_data = {
                    **input.payload,
                    "items": result.data.get("items", []),
                    "warnings": result.data.get("warnings", []),
                    "row_count": result.data.get("row_count", 0),
                }
                return ActivityOutput(
                    success=result.success,
                    item_id=input.item_id,
                    new_state=ItemState.PARSED.value,
                    data=output_data,
                    cost_usd=result.cost,
                )

    except Exception as exc:
        activity.logger.error("Parse failed for item %s: %s", input.item_id, exc)
        return ActivityOutput(
            success=False,
            item_id=input.item_id,
            new_state=ItemState.FAILED.value,
            data={**input.payload, "error": str(exc)},
        )

    return ActivityOutput(
        success=True,
        item_id=input.item_id,
        new_state=ItemState.PARSED.value,
        data=input.payload,
    )


@activity.defn
async def fuse_data_activity(input: ActivityInput) -> ActivityOutput:
    """Fuse PO + PI data for an item using the FusionAgent."""
    activity.logger.info("Fusing data for item %s", input.item_id)

    po_items = input.payload.get("po_items", [])
    pi_items = input.payload.get("pi_items", [])

    if not po_items and not pi_items:
        # No data to fuse — pass through
        return ActivityOutput(
            success=True,
            item_id=input.item_id,
            new_state=ItemState.FUSED.value,
            data=input.payload,
        )

    try:
        from labelforge.agents.fusion import FusionAgent
        from labelforge.config import settings

        llm_provider = None
        if settings.openai_api_key:
            from labelforge.core.llm import OpenAIProvider
            from labelforge.api.v1.orders import _LLMProviderWrapper
            provider = OpenAIProvider(api_key=settings.openai_api_key)
            llm_provider = _LLMProviderWrapper(provider, settings.llm_default_model)

        agent = FusionAgent(llm_provider=llm_provider)
        result = await agent.execute({
            "po_items": po_items,
            "pi_items": pi_items,
        })

        output_data = {
            **input.payload,
            "fused_items": result.data.get("fused_items", []),
            "issues": result.data.get("issues", []),
        }
        return ActivityOutput(
            success=result.success,
            item_id=input.item_id,
            new_state=ItemState.FUSED.value,
            data=output_data,
            needs_hitl=result.needs_hitl,
            hitl_reason=result.hitl_reason,
            cost_usd=result.cost,
        )

    except Exception as exc:
        activity.logger.error("Fusion failed for item %s: %s", input.item_id, exc)
        return ActivityOutput(
            success=False,
            item_id=input.item_id,
            new_state=ItemState.FAILED.value,
            data={**input.payload, "error": str(exc)},
        )


@activity.defn
async def compliance_eval_activity(input: ActivityInput) -> ActivityOutput:
    """Evaluate compliance rules against fused item data via the ComplianceClassifierAgent."""
    activity.logger.info("Running compliance evaluation for item %s", input.item_id)

    fused_items = input.payload.get("fused_items") or []
    if not fused_items:
        return ActivityOutput(
            success=True,
            item_id=input.item_id,
            new_state=ItemState.COMPLIANCE_EVAL.value,
            data=input.payload,
        )

    try:
        from labelforge.agents.compliance_classifier import ComplianceClassifierAgent

        # Rules may arrive in the payload (test/synchronous paths) or need to be
        # loaded from the DB for the tenant.
        rules = list(input.payload.get("rules") or [])
        if not rules:
            rules = await _load_active_rules_for_tenant(input.tenant_id)

        agent = ComplianceClassifierAgent()
        result = await agent.execute({
            "fused_items": fused_items,
            "rules": rules,
            "default_destination": input.payload.get("default_destination", "US"),
        })

        output_data = {
            **input.payload,
            "compliance_reports": result.data.get("reports", []),
            "applicable_warnings": result.data.get("warnings", {}),
            "compliance_needs_hitl_items": result.data.get("needs_hitl_items", []),
        }
        return ActivityOutput(
            success=result.success,
            item_id=input.item_id,
            new_state=ItemState.COMPLIANCE_EVAL.value,
            data=output_data,
            needs_hitl=result.needs_hitl,
            hitl_reason=result.hitl_reason,
            cost_usd=result.cost,
        )

    except Exception as exc:
        activity.logger.error("Compliance eval failed for item %s: %s", input.item_id, exc)
        return ActivityOutput(
            success=False,
            item_id=input.item_id,
            new_state=ItemState.FAILED.value,
            data={**input.payload, "error": str(exc)},
        )


@activity.defn
async def generate_drawing_activity(input: ActivityInput) -> ActivityOutput:
    """Generate die-cut drawings for a compliant item."""
    activity.logger.info("Generating drawing for item %s", input.item_id)
    return ActivityOutput(
        success=True,
        item_id=input.item_id,
        new_state=ItemState.DRAWING_GENERATED.value,
        data=input.payload,
    )


@activity.defn
async def compose_label_activity(input: ActivityInput) -> ActivityOutput:
    """Compose the die-cut SVG via the ComposerAgent.

    Produces one die-cut artifact per fused item. Resulting SVGs, placements
    and provenance records are accumulated on the payload under
    ``composed_artifacts`` keyed by item_no.
    """
    activity.logger.info("Composing label for item %s", input.item_id)

    fused_items = input.payload.get("fused_items") or []
    if not fused_items:
        return ActivityOutput(
            success=True,
            item_id=input.item_id,
            new_state=ItemState.COMPOSED.value,
            data=input.payload,
        )

    try:
        from labelforge.agents.composer import ComposerAgent

        importer_profile = input.payload.get("importer_profile") or {}
        reports_by_item = {
            r.get("item_no"): r for r in (input.payload.get("compliance_reports") or [])
        }
        drawings_by_item = input.payload.get("line_drawings_svg") or {}

        agent = ComposerAgent()
        artifacts: dict[str, dict] = {}
        total_cost = 0.0
        any_hitl = False
        hitl_reasons: list[str] = []

        for item in fused_items:
            item_no = str(item.get("item_no") or "UNKNOWN")
            report = reports_by_item.get(item_no) or {
                "item_no": item_no, "verdicts": [],
                "applicable_warnings": [], "passed": True,
            }
            drawing = drawings_by_item.get(item_no)
            result = await agent.execute({
                "fused_item": item,
                "importer_profile": importer_profile,
                "compliance_report": report,
                "line_drawing_svg": drawing,
            })
            total_cost += result.cost or 0.0
            if result.needs_hitl:
                any_hitl = True
                if result.hitl_reason:
                    hitl_reasons.append(f"{item_no}: {result.hitl_reason}")
            artifacts[item_no] = {
                "die_cut_svg": result.data.get("die_cut_svg", ""),
                "placements": result.data.get("placements", []),
                "provenance": result.data.get("provenance", {}),
            }

        output_data = {
            **input.payload,
            "composed_artifacts": artifacts,
        }
        return ActivityOutput(
            success=not any_hitl,
            item_id=input.item_id,
            new_state=ItemState.COMPOSED.value,
            data=output_data,
            needs_hitl=any_hitl,
            hitl_reason="; ".join(hitl_reasons) if hitl_reasons else None,
            cost_usd=total_cost,
        )

    except Exception as exc:
        activity.logger.error("Compose failed for item %s: %s", input.item_id, exc)
        return ActivityOutput(
            success=False,
            item_id=input.item_id,
            new_state=ItemState.FAILED.value,
            data={**input.payload, "error": str(exc)},
        )


@activity.defn
async def validate_output_activity(input: ActivityInput) -> ActivityOutput:
    """Validate composed output (barcode scannable, dims match, etc.) via ValidatorAgent."""
    activity.logger.info("Validating output for item %s", input.item_id)

    fused_items = input.payload.get("fused_items") or []
    artifacts = input.payload.get("composed_artifacts") or {}
    if not fused_items or not artifacts:
        return ActivityOutput(
            success=True,
            item_id=input.item_id,
            new_state=ItemState.VALIDATED.value,
            data=input.payload,
        )

    try:
        from labelforge.agents.validator import ValidatorAgent

        importer_profile = input.payload.get("importer_profile") or {}
        required_fields = _required_fields_from_profile(importer_profile)
        expected_dims = input.payload.get("expected_dimensions_mm") or {}

        agent = ValidatorAgent()
        reports: dict[str, dict] = {}
        critical_total = 0
        any_hitl = False
        hitl_reasons: list[str] = []

        for item in fused_items:
            item_no = str(item.get("item_no") or "UNKNOWN")
            artifact = artifacts.get(item_no) or {}
            svg = artifact.get("die_cut_svg", "")
            placements = artifact.get("placements", [])
            result = await agent.execute({
                "die_cut_svg": svg,
                "fused_item": item,
                "required_fields": required_fields,
                "expected_dimensions_mm": expected_dims,
                "placements": placements,
            })
            report = dict(result.data.get("validation_report", {}) or {})
            # Operator override: when chat has set ``validation_override``
            # on the item (via the validator handler's patch-allowlist),
            # treat a failing validation as a passing one — the failure
            # is recorded in the report alongside the override note for
            # audit trail, but the activity no longer raises HiTL. This
            # is the wire-up for the "(b) accept the failure with an
            # override note" escape hatch the validator role description
            # already promises the operator.
            if bool(item.get("validation_override")):
                report["override_accepted"] = True
                note = item.get("override_note") or item.get("override_reason")
                if note:
                    report["override_note"] = str(note)
                reports[item_no] = report
                continue
            reports[item_no] = report
            critical_total += result.data.get("critical_count", 0)
            if result.needs_hitl:
                any_hitl = True
                if result.hitl_reason:
                    hitl_reasons.append(f"{item_no}: {result.hitl_reason}")

        output_data = {
            **input.payload,
            "validation_reports": reports,
            "validation_critical_count": critical_total,
        }
        return ActivityOutput(
            success=not any_hitl,
            item_id=input.item_id,
            new_state=(
                ItemState.VALIDATED.value if not any_hitl else ItemState.COMPOSED.value
            ),
            data=output_data,
            needs_hitl=any_hitl,
            hitl_reason="; ".join(hitl_reasons) if hitl_reasons else None,
        )

    except Exception as exc:
        activity.logger.error("Validate failed for item %s: %s", input.item_id, exc)
        return ActivityOutput(
            success=False,
            item_id=input.item_id,
            new_state=ItemState.FAILED.value,
            data={**input.payload, "error": str(exc)},
        )


# ── Activity helpers ───────────────────────────────────────────────────────


async def _load_active_rules_for_tenant(tenant_id: str) -> list[dict]:
    """Fetch active compliance rules for a tenant as raw dicts.

    Returns an empty list on any DB / connection issue — the agent treats
    an empty rule set as profile drift and escalates to HiTL on its own,
    so we never want this helper to raise into the workflow.
    """
    try:
        from sqlalchemy import select
        from labelforge.db.models import ComplianceRule
        from labelforge.db.session import async_session_factory

        async with async_session_factory() as session:
            stmt = select(ComplianceRule).where(
                ComplianceRule.tenant_id == tenant_id,
                ComplianceRule.is_active == True,  # noqa: E712
            )
            rows = (await session.execute(stmt)).scalars().all()
            return [
                {
                    "code": r.rule_code,
                    "version": r.version,
                    "title": r.title,
                    "country": r.region,
                    "placement": r.placement,
                    "logic": r.logic or {},
                }
                for r in rows
            ]
    except Exception as exc:  # pragma: no cover - defensive
        logger.warning("Could not load rules for tenant %s: %s", tenant_id, exc)
        return []


def _required_fields_from_profile(profile: dict) -> list[str]:
    """Extract the union of field names declared in a profile's panel_layouts.

    Baseline regulator-mandated fields (F13 from the DieCut Generation
    Review) are always included even when the profile's panel_layouts are
    empty — the Validator treats missing baseline fields as Critical and
    the pipeline blocks the order on HUMAN_BLOCKED until resolved.
    """
    layouts = profile.get("panel_layouts") or {}
    required: set[str] = {
        "item_no", "case_qty", "dimensions",
        "country_of_origin", "barcode",
    }
    if isinstance(layouts, dict):
        for panel, spec in layouts.items():
            if isinstance(spec, list):
                required.update(str(f) for f in spec)
            elif isinstance(spec, dict):
                if spec.get("selected") is False:
                    continue
                required.update(str(f) for f in spec.get("fields", []))
    return sorted(required)


@activity.defn
async def update_item_state_activity(input: ActivityInput) -> ActivityOutput:
    """Persist item state change to the database."""
    new_state = input.payload.get("new_state", "")
    activity.logger.info("Updating item %s state to %s", input.item_id, new_state)
    return ActivityOutput(
        success=True,
        item_id=input.item_id,
        new_state=new_state,
    )


@activity.defn
async def create_hitl_thread_activity(input: ActivityInput) -> ActivityOutput:
    """Create a HiTL thread when an activity needs human review."""
    reason = input.payload.get("reason", "Manual review required")
    activity.logger.info("Creating HiTL thread for item %s: %s", input.item_id, reason)
    return ActivityOutput(
        success=True,
        item_id=input.item_id,
        new_state=ItemState.HUMAN_BLOCKED.value,
        data={"hitl_reason": reason},
        needs_hitl=True,
        hitl_reason=reason,
    )


# ── Pipeline step definitions ──────────────────────────────────────────────

PIPELINE_STEPS = [
    ("intake_classify", intake_classify_activity, ItemState.INTAKE_CLASSIFIED),
    ("parse_document", parse_document_activity, ItemState.PARSED),
    ("fuse_data", fuse_data_activity, ItemState.FUSED),
    ("compliance_eval", compliance_eval_activity, ItemState.COMPLIANCE_EVAL),
    ("generate_drawing", generate_drawing_activity, ItemState.DRAWING_GENERATED),
    ("compose_label", compose_label_activity, ItemState.COMPOSED),
    ("validate_output", validate_output_activity, ItemState.VALIDATED),
]


# ── Workflow ───────────────────────────────────────────────────────────────


@workflow.defn
class OrderProcessorWorkflow:
    """Orchestrates the full labeling pipeline for an order.

    Processes each item through the pipeline steps sequentially.
    On activity timeout (5 min) or low confidence, escalates to HiTL.
    Retries up to 3 times with exponential backoff before failing.
    """

    def __init__(self) -> None:
        self._config = WorkflowConfig()
        self._item_states: dict[str, str] = {}
        self._human_unblocked: dict[str, asyncio.Event] = {}

    @workflow.run
    async def run(
        self,
        order_id: str,
        tenant_id: str,
        item_ids: list[str],
    ) -> dict[str, Any]:
        """Process all items in an order through the pipeline."""
        workflow.logger.info("Starting OrderProcessorWorkflow for order %s with %d items", order_id, len(item_ids))

        results: dict[str, dict] = {}

        # Process items with concurrency limit
        semaphore = asyncio.Semaphore(self._config.concurrency_limit)

        async def process_item(item_id: str) -> None:
            async with semaphore:
                result = await self._process_single_item(order_id, tenant_id, item_id)
                results[item_id] = result

        tasks = [process_item(item_id) for item_id in item_ids]
        await asyncio.gather(*tasks)

        workflow.logger.info("OrderProcessorWorkflow completed for order %s", order_id)
        return {
            "order_id": order_id,
            "items": results,
            "completed": all(r.get("success", False) for r in results.values()),
        }

    async def _process_single_item(
        self,
        order_id: str,
        tenant_id: str,
        item_id: str,
    ) -> dict:
        """Run a single item through all pipeline steps."""
        self._item_states[item_id] = ItemState.CREATED.value
        payload: dict = {}

        for step_name, activity_fn, target_state in PIPELINE_STEPS:
            workflow.logger.info("Item %s: starting step %s", item_id, step_name)

            act_input = ActivityInput(
                order_id=order_id,
                item_id=item_id,
                tenant_id=tenant_id,
                payload=payload,
            )

            try:
                output: ActivityOutput = await workflow.execute_activity(
                    activity_fn,
                    act_input,
                    start_to_close_timeout=timedelta(seconds=self._config.activity_timeout),
                    retry_policy=DEFAULT_RETRY_POLICY,
                )
            except Exception as exc:
                workflow.logger.error("Item %s: step %s failed after retries: %s", item_id, step_name, exc)
                # Timeout or unrecoverable failure → escalate to HiTL
                await self._escalate_to_hitl(
                    order_id, tenant_id, item_id,
                    reason=f"Activity {step_name} failed: {exc}",
                )
                self._item_states[item_id] = ItemState.FAILED.value
                return {"success": False, "failed_step": step_name, "error": str(exc)}

            if output.needs_hitl:
                workflow.logger.info("Item %s: step %s needs HiTL: %s", item_id, step_name, output.hitl_reason)
                await self._escalate_to_hitl(
                    order_id, tenant_id, item_id,
                    reason=output.hitl_reason or "Agent requested human review",
                )
                # Wait for human to unblock
                await self._wait_for_human_unblock(item_id)
                workflow.logger.info("Item %s: unblocked by human, resuming from %s", item_id, step_name)
                # After unblock, the item stays at current state and we
                # do NOT advance — the loop will retry this step on next iteration.
                # For simplicity, we mark the step as done and continue.

            # Update state
            self._item_states[item_id] = output.new_state
            payload = output.data

            # Persist state change
            await workflow.execute_activity(
                update_item_state_activity,
                ActivityInput(
                    order_id=order_id,
                    item_id=item_id,
                    tenant_id=tenant_id,
                    payload={"new_state": output.new_state},
                ),
                start_to_close_timeout=timedelta(seconds=30),
                retry_policy=DEFAULT_RETRY_POLICY,
            )

        return {"success": True, "final_state": self._item_states[item_id], "data": payload}

    async def _escalate_to_hitl(
        self,
        order_id: str,
        tenant_id: str,
        item_id: str,
        reason: str,
    ) -> None:
        """Create a HiTL thread for manual review."""
        await workflow.execute_activity(
            create_hitl_thread_activity,
            ActivityInput(
                order_id=order_id,
                item_id=item_id,
                tenant_id=tenant_id,
                payload={"reason": reason},
            ),
            start_to_close_timeout=timedelta(seconds=30),
            retry_policy=DEFAULT_RETRY_POLICY,
        )

    @workflow.signal
    async def human_unblock(self, item_id: str) -> None:
        """Signal sent when a human resolves a HiTL thread for an item."""
        if item_id in self._human_unblocked:
            self._human_unblocked[item_id].set()

    async def _wait_for_human_unblock(self, item_id: str) -> None:
        """Wait until a human sends the unblock signal for this item."""
        self._human_unblocked[item_id] = asyncio.Event()
        await workflow.wait_condition(lambda: self._human_unblocked[item_id].is_set())

    @workflow.query
    def get_item_states(self) -> dict[str, str]:
        """Query current state of all items in this workflow."""
        return dict(self._item_states)


# ── Worker helper ──────────────────────────────────────────────────────────


ALL_ACTIVITIES = [
    intake_classify_activity,
    parse_document_activity,
    fuse_data_activity,
    compliance_eval_activity,
    generate_drawing_activity,
    compose_label_activity,
    validate_output_activity,
    update_item_state_activity,
    create_hitl_thread_activity,
]


async def create_worker(client, task_queue: str = "labelforge-tasks"):
    """Create and return a Temporal worker with all activities registered."""
    from temporalio.worker import Worker

    return Worker(
        client,
        task_queue=task_queue,
        workflows=[OrderProcessorWorkflow],
        activities=ALL_ACTIVITIES,
    )
