"""Agent inspector endpoints (INT-013 · Sprint-16).

Lists the 14 labelforge agents (canonical catalogue) and surfaces
per-agent live telemetry — calls, success rate, average latency, total
cost and last-call timestamp. Telemetry is gathered from
:class:`labelforge.agents.registry.AgentRegistry`, which is populated
automatically by :class:`labelforge.agents.base.BaseAgent`.
"""
from __future__ import annotations

from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from labelforge.agents.registry import AGENT_CATALOGUE, get_registry
from labelforge.api.v1.auth import get_current_user
from labelforge.core.auth import TokenPayload


router = APIRouter(prefix="/agents", tags=["agents"])


class AgentCard(BaseModel):
    agent_id: str
    name: str
    kind: str
    status: str  # "healthy" | "degraded" | "idle"
    calls: int
    successes: int
    failures: int
    success_rate: float  # 0.0 - 1.0
    avg_latency_ms: float
    total_cost_usd: float
    last_call_at: Optional[float] = None  # unix-seconds


class AgentListResponse(BaseModel):
    agents: List[AgentCard]
    total: int


def _status_for(calls: int, failures: int) -> str:
    if calls == 0:
        return "idle"
    if failures == 0:
        return "healthy"
    if failures / calls >= 0.25:
        return "degraded"
    return "healthy"


def _card_for(entry: dict) -> AgentCard:
    snap = get_registry().snapshot(entry["agent_id"])
    calls = snap.calls
    successes = snap.successes
    failures = snap.failures
    success_rate = (successes / calls) if calls else 0.0
    avg_latency_ms = (snap.total_duration_s * 1000 / calls) if calls else 0.0
    return AgentCard(
        agent_id=entry["agent_id"],
        name=entry["name"],
        kind=entry["kind"],
        status=_status_for(calls, failures),
        calls=calls,
        successes=successes,
        failures=failures,
        success_rate=round(success_rate, 4),
        avg_latency_ms=round(avg_latency_ms, 2),
        total_cost_usd=round(snap.total_cost_usd, 6),
        last_call_at=snap.last_call_at,
    )


@router.get("", response_model=AgentListResponse)
async def list_agents(
    _user: TokenPayload = Depends(get_current_user),
) -> AgentListResponse:
    cards = [_card_for(entry) for entry in AGENT_CATALOGUE]
    return AgentListResponse(agents=cards, total=len(cards))


@router.get("/{agent_id}", response_model=AgentCard)
async def get_agent(
    agent_id: str,
    _user: TokenPayload = Depends(get_current_user),
) -> AgentCard:
    entry = next((a for a in AGENT_CATALOGUE if a["agent_id"] == agent_id), None)
    if entry is None:
        raise HTTPException(status_code=404, detail=f"Unknown agent_id: {agent_id}")
    return _card_for(entry)
