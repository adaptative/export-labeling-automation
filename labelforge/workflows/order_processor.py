"""Order processing workflow — state machine."""
from labelforge.contracts.models import ItemState, OrderState, OrderItem, compute_order_state
from dataclasses import dataclass
from typing import Optional

MAX_RETRIES = 3
ACTIVITY_TIMEOUT_SECONDS = 300  # 5 minutes


@dataclass
class WorkflowConfig:
    max_retries: int = MAX_RETRIES
    activity_timeout: int = ACTIVITY_TIMEOUT_SECONDS
    concurrency_limit: int = 8


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
