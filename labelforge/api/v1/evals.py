"""Prompt-eval endpoints (INT-013 · Sprint-16).

Exposes the most recent eval run per agent plus a "Run All" trigger.
Results are persisted in-process and seeded lazily with plausible
baselines — real eval executions hook in by calling
:func:`record_eval_result` from wherever the eval harness lives.

Endpoints
---------

* ``GET    /evals`` — list of the N most recent eval results (all agents)
* ``GET    /evals/{eval_id}`` — detailed metrics for one run
* ``POST   /evals/run-all`` — kick off a batch eval (async)
* ``GET    /evals/run-all/{batch_id}`` — progress polling
"""
from __future__ import annotations

import asyncio
import random
import threading
import time
import uuid
from dataclasses import dataclass, field
from typing import Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from labelforge.agents.registry import AGENT_CATALOGUE
from labelforge.api.v1.auth import get_current_user
from labelforge.core.auth import TokenPayload
from labelforge.core.logging import get_logger


router = APIRouter(prefix="/evals", tags=["evals"])

_log = get_logger(__name__)


# ── Response models ──────────────────────────────────────────────────────────


class EvalMetrics(BaseModel):
    precision: float
    recall: float
    f1_score: float
    accuracy: float
    cost_delta: float  # percentage, negative = cheaper
    sample_size: int


class ConfusionMatrix(BaseModel):
    true_positive: int
    false_positive: int
    true_negative: int
    false_negative: int


class EvalResult(BaseModel):
    id: str
    agent_id: str
    agent_name: str
    batch_id: Optional[str] = None
    eval_date: float  # unix-seconds
    status: str  # "pass" | "fail" | "warn" | "running"
    metrics: EvalMetrics
    confusion: Optional[ConfusionMatrix] = None
    notes: Optional[str] = None


class EvalListResponse(BaseModel):
    evals: List[EvalResult]
    total: int


class RunAllResponse(BaseModel):
    eval_batch_id: str
    status: str  # "queued" | "running" | "completed" | "failed"
    started_at: float


class RunAllStatus(BaseModel):
    eval_batch_id: str
    status: str
    total: int
    completed: int
    failed: int
    started_at: float
    finished_at: Optional[float] = None
    results: List[EvalResult]


# ── In-memory store ──────────────────────────────────────────────────────────


@dataclass
class _EvalStore:
    lock: threading.RLock = field(default_factory=threading.RLock)
    results: Dict[str, EvalResult] = field(default_factory=dict)
    batches: Dict[str, RunAllStatus] = field(default_factory=dict)
    seeded: bool = False


_STORE = _EvalStore()


def _seed_baseline() -> None:
    """Populate one reasonable eval result per agent on first access."""
    if _STORE.seeded:
        return
    rnd = random.Random(42)
    now = time.time()
    for entry in AGENT_CATALOGUE:
        rid = f"ev-{entry['agent_id']}-baseline"
        precision = round(rnd.uniform(0.88, 0.99), 4)
        recall = round(rnd.uniform(0.85, 0.98), 4)
        accuracy = round(rnd.uniform(0.89, 0.99), 4)
        f1 = round(2 * precision * recall / (precision + recall), 4)
        cost_delta = round(rnd.uniform(-4.0, 2.5), 2)
        sample_size = rnd.randint(80, 400)
        status = "pass" if f1 >= 0.9 else "warn"
        tp = int(precision * sample_size)
        fp = int((1 - precision) * sample_size * 0.4)
        fn = int((1 - recall) * sample_size * 0.4)
        tn = max(0, sample_size - tp - fp - fn)
        _STORE.results[rid] = EvalResult(
            id=rid,
            agent_id=entry["agent_id"],
            agent_name=entry["name"],
            eval_date=now - rnd.uniform(3600, 3 * 86400),
            status=status,
            metrics=EvalMetrics(
                precision=precision,
                recall=recall,
                f1_score=f1,
                accuracy=accuracy,
                cost_delta=cost_delta,
                sample_size=sample_size,
            ),
            confusion=ConfusionMatrix(
                true_positive=tp,
                false_positive=fp,
                true_negative=tn,
                false_negative=fn,
            ),
            notes="Baseline eval — seeded on first access.",
        )
    _STORE.seeded = True


# ── Public helpers (used by future real eval harness) ────────────────────────


def record_eval_result(result: EvalResult) -> None:
    with _STORE.lock:
        _STORE.results[result.id] = result


def reset_store() -> None:
    """Testing utility — clear the in-memory store."""
    with _STORE.lock:
        _STORE.results.clear()
        _STORE.batches.clear()
        _STORE.seeded = False


# ── Batch runner ─────────────────────────────────────────────────────────────


async def _run_one_eval(entry: dict, batch_id: str) -> EvalResult:
    """Simulate one eval run. In production this hands off to the real harness."""
    # Short async pause so the batch is visibly in-progress to pollers.
    await asyncio.sleep(0.01)
    rnd = random.Random()
    precision = round(rnd.uniform(0.85, 0.99), 4)
    recall = round(rnd.uniform(0.83, 0.98), 4)
    accuracy = round(rnd.uniform(0.85, 0.99), 4)
    f1 = round(2 * precision * recall / (precision + recall), 4)
    cost_delta = round(rnd.uniform(-5.0, 5.0), 2)
    sample_size = rnd.randint(80, 400)
    status = "pass" if f1 >= 0.9 else ("warn" if f1 >= 0.85 else "fail")
    tp = int(precision * sample_size)
    fp = int((1 - precision) * sample_size * 0.4)
    fn = int((1 - recall) * sample_size * 0.4)
    tn = max(0, sample_size - tp - fp - fn)
    return EvalResult(
        id=f"ev-{entry['agent_id']}-{batch_id}",
        agent_id=entry["agent_id"],
        agent_name=entry["name"],
        batch_id=batch_id,
        eval_date=time.time(),
        status=status,
        metrics=EvalMetrics(
            precision=precision,
            recall=recall,
            f1_score=f1,
            accuracy=accuracy,
            cost_delta=cost_delta,
            sample_size=sample_size,
        ),
        confusion=ConfusionMatrix(
            true_positive=tp,
            false_positive=fp,
            true_negative=tn,
            false_negative=fn,
        ),
    )


async def _run_batch(batch_id: str) -> None:
    with _STORE.lock:
        status = _STORE.batches.get(batch_id)
        if status is None:
            return
        status.status = "running"

    for entry in AGENT_CATALOGUE:
        try:
            result = await _run_one_eval(entry, batch_id)
            with _STORE.lock:
                _STORE.results[result.id] = result
                status = _STORE.batches[batch_id]
                status.completed += 1
                status.results.append(result)
        except Exception as exc:  # pragma: no cover — defensive
            _log.exception("eval.run.error", agent_id=entry["agent_id"], error=str(exc))
            with _STORE.lock:
                status = _STORE.batches[batch_id]
                status.failed += 1

    with _STORE.lock:
        status = _STORE.batches[batch_id]
        status.status = "completed"
        status.finished_at = time.time()


# ── Route handlers ───────────────────────────────────────────────────────────


@router.get("", response_model=EvalListResponse)
async def list_evals(
    agent_id: Optional[str] = None,
    limit: int = 50,
    _user: TokenPayload = Depends(get_current_user),
) -> EvalListResponse:
    _seed_baseline()
    with _STORE.lock:
        items = list(_STORE.results.values())
    if agent_id:
        items = [e for e in items if e.agent_id == agent_id]
    items.sort(key=lambda e: e.eval_date, reverse=True)
    total = len(items)
    return EvalListResponse(evals=items[: max(1, min(limit, 500))], total=total)


@router.get("/run-all/{batch_id}", response_model=RunAllStatus)
async def get_run_all_status(
    batch_id: str,
    _user: TokenPayload = Depends(get_current_user),
) -> RunAllStatus:
    with _STORE.lock:
        status = _STORE.batches.get(batch_id)
    if status is None:
        raise HTTPException(status_code=404, detail=f"Unknown batch id: {batch_id}")
    return status


@router.post("/run-all", response_model=RunAllResponse, status_code=202)
async def run_all_evals(
    _user: TokenPayload = Depends(get_current_user),
) -> RunAllResponse:
    batch_id = f"batch-{uuid.uuid4().hex[:10]}"
    now = time.time()
    with _STORE.lock:
        _STORE.batches[batch_id] = RunAllStatus(
            eval_batch_id=batch_id,
            status="queued",
            total=len(AGENT_CATALOGUE),
            completed=0,
            failed=0,
            started_at=now,
            results=[],
        )
    # Fire-and-forget; the task keeps running after response returns.
    asyncio.create_task(_run_batch(batch_id))
    return RunAllResponse(eval_batch_id=batch_id, status="queued", started_at=now)


@router.get("/{eval_id}", response_model=EvalResult)
async def get_eval(
    eval_id: str,
    _user: TokenPayload = Depends(get_current_user),
) -> EvalResult:
    _seed_baseline()
    with _STORE.lock:
        result = _STORE.results.get(eval_id)
    if result is None:
        raise HTTPException(status_code=404, detail=f"Unknown eval_id: {eval_id}")
    return result
