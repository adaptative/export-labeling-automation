"""Tests for the order processing workflow — state machine + Temporal contracts."""
import pytest
from labelforge.contracts.models import ItemState, OrderState, OrderItem, compute_order_state
from labelforge.workflows.order_processor import (
    STATE_TRANSITIONS, WorkflowConfig, is_valid_transition, transition_item,
    MAX_RETRIES, ACTIVITY_TIMEOUT_SECONDS,
    ActivityInput, ActivityOutput, DEFAULT_RETRY_POLICY, PIPELINE_STEPS,
    ALL_ACTIVITIES,
)


# ── ItemState enum ───────────────────────────────────────────────────────────


def test_item_state_has_12_values():
    assert len(ItemState) == 12


# ── Transition validity ─────────────────────────────────────────────────────


def test_valid_transitions_from_created():
    assert is_valid_transition(ItemState.CREATED, ItemState.INTAKE_CLASSIFIED)
    assert is_valid_transition(ItemState.CREATED, ItemState.HUMAN_BLOCKED)
    assert is_valid_transition(ItemState.CREATED, ItemState.FAILED)


def test_invalid_transition_raises_value_error():
    item = OrderItem(id="i1", order_id="o1", item_no="001", state=ItemState.CREATED)
    with pytest.raises(ValueError, match="Invalid transition"):
        transition_item(item, ItemState.DELIVERED)


def test_delivered_is_terminal():
    allowed = STATE_TRANSITIONS[ItemState.DELIVERED]
    assert allowed == []


def test_failed_is_terminal():
    allowed = STATE_TRANSITIONS[ItemState.FAILED]
    assert allowed == []


def test_human_blocked_can_resume_to_prior_states():
    allowed = STATE_TRANSITIONS[ItemState.HUMAN_BLOCKED]
    assert ItemState.CREATED in allowed
    assert ItemState.INTAKE_CLASSIFIED in allowed
    assert ItemState.PARSED in allowed
    assert ItemState.FUSED in allowed
    assert ItemState.COMPLIANCE_EVAL in allowed
    assert ItemState.DRAWING_GENERATED in allowed
    assert ItemState.COMPOSED in allowed


def test_composed_can_self_transition():
    assert is_valid_transition(ItemState.COMPOSED, ItemState.COMPOSED)
    item = OrderItem(id="i1", order_id="o1", item_no="001", state=ItemState.COMPOSED)
    result = transition_item(item, ItemState.COMPOSED)
    assert result.state == ItemState.COMPOSED


# ── compute_order_state ──────────────────────────────────────────────────────


def _make_item(state: ItemState) -> OrderItem:
    return OrderItem(id="x", order_id="o1", item_no="001", state=state)


def test_compute_order_state_any_failed_is_attention():
    items = [_make_item(ItemState.DELIVERED), _make_item(ItemState.FAILED)]
    assert compute_order_state(items) == OrderState.ATTENTION


def test_compute_order_state_all_delivered():
    items = [_make_item(ItemState.DELIVERED), _make_item(ItemState.DELIVERED)]
    assert compute_order_state(items) == OrderState.DELIVERED


def test_compute_order_state_any_human_blocked():
    items = [_make_item(ItemState.PARSED), _make_item(ItemState.HUMAN_BLOCKED)]
    assert compute_order_state(items) == OrderState.HUMAN_BLOCKED


def test_compute_order_state_all_reviewed_or_delivered_is_ready():
    items = [_make_item(ItemState.REVIEWED), _make_item(ItemState.DELIVERED)]
    assert compute_order_state(items) == OrderState.READY_TO_DELIVER


def test_compute_order_state_mixed_is_in_progress():
    items = [_make_item(ItemState.PARSED), _make_item(ItemState.FUSED)]
    assert compute_order_state(items) == OrderState.IN_PROGRESS


# ── WorkflowConfig ───────────────────────────────────────────────────────────


def test_workflow_config_defaults():
    config = WorkflowConfig()
    assert config.max_retries == MAX_RETRIES
    assert config.activity_timeout == ACTIVITY_TIMEOUT_SECONDS
    assert config.concurrency_limit == 8


# ── ActivityInput / ActivityOutput contracts ──────────────────────────────────


def test_activity_input_defaults():
    inp = ActivityInput(order_id="o1", item_id="i1", tenant_id="t1")
    assert inp.document_id is None
    assert inp.payload == {}


def test_activity_input_with_payload():
    inp = ActivityInput(
        order_id="o1", item_id="i1", tenant_id="t1",
        payload={"doc_content": "hello"},
    )
    assert inp.payload["doc_content"] == "hello"


def test_activity_output_success():
    out = ActivityOutput(
        success=True, item_id="i1",
        new_state=ItemState.INTAKE_CLASSIFIED.value,
    )
    assert out.success is True
    assert out.needs_hitl is False
    assert out.cost_usd == 0.0


def test_activity_output_hitl():
    out = ActivityOutput(
        success=False, item_id="i1",
        new_state=ItemState.HUMAN_BLOCKED.value,
        needs_hitl=True,
        hitl_reason="Low confidence",
    )
    assert out.needs_hitl is True
    assert out.hitl_reason == "Low confidence"


# ── Retry policy ────────────────────────────────────────────────────────────


def test_retry_policy_max_attempts():
    assert DEFAULT_RETRY_POLICY.maximum_attempts == MAX_RETRIES


def test_retry_policy_backoff_coefficient():
    assert DEFAULT_RETRY_POLICY.backoff_coefficient == 2.0


# ── Pipeline steps ──────────────────────────────────────────────────────────


def test_pipeline_has_7_steps():
    assert len(PIPELINE_STEPS) == 7


def test_pipeline_step_names():
    names = [name for name, _, _ in PIPELINE_STEPS]
    assert names == [
        "intake_classify",
        "parse_document",
        "fuse_data",
        "compliance_eval",
        "generate_drawing",
        "compose_label",
        "validate_output",
    ]


def test_pipeline_target_states():
    states = [state.value for _, _, state in PIPELINE_STEPS]
    assert states == [
        "INTAKE_CLASSIFIED",
        "PARSED",
        "FUSED",
        "COMPLIANCE_EVAL",
        "DRAWING_GENERATED",
        "COMPOSED",
        "VALIDATED",
    ]


# ── All activities registered ───────────────────────────────────────────────


def test_all_activities_count():
    assert len(ALL_ACTIVITIES) == 9


def test_all_activities_are_callable():
    for act in ALL_ACTIVITIES:
        assert callable(act)
