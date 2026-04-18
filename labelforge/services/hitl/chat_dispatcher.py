"""HITL chat dispatcher — fires the agent-side reply loop.

When :meth:`labelforge.services.hitl.resolver.ThreadResolver.add_message`
persists a ``human`` message, it schedules :func:`dispatch_on_human_message`
as a fire-and-forget asyncio task. The dispatcher:

1. Re-loads the thread + item + full message history.
2. Looks up the per-agent chat handler
   (:func:`labelforge.agents.chat.get_chat_handler`).
3. Calls ``handler.respond(ctx)``.
4. Applies any proposed ``item.data`` patches (allowlist-enforced inside
   the handler).
5. Persists the agent's reply as a new ``agent`` message — which goes
   through the *same* resolver but skips the re-dispatch (otherwise we'd
   loop).
6. If the handler signalled ``resolved``, auto-closes the thread and
   kicks the pipeline-advance hook so the item can make forward progress
   without an operator click.

Safety rails
------------
* **Recursion guard** — dispatch only fires on ``human`` messages. The
  resolver decides this based on ``sender_type``.
* **Per-thread lock** — at most one dispatcher run per thread at a time.
  If the operator sends two messages in quick succession, the second
  reply waits for the first to finish so the LLM sees the full history.
* **Turn cap** — hard stop at :data:`MAX_AGENT_TURNS` agent replies per
  thread. Protects against a buggy handler that keeps responding
  ``resolved: false`` to itself.
* **Idle on terminal status** — if a dispatcher wakes up after the
  thread is already RESOLVED / ESCALATED it no-ops.
"""
from __future__ import annotations

import asyncio
import logging
import sys
from typing import Any, Dict, Mapping, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from labelforge.agents.chat import (
    ChatContext,
    ChatMessage,
    ChatReply,
    get_chat_handler,
)
from labelforge.db import session as _session_mod
from labelforge.db.models import (
    HiTLMessageModel,
    HiTLThreadModel,
    OrderItemModel,
)

logger = logging.getLogger(__name__)


# Hard cap on agent replies per thread. A normal block-resolution
# conversation is 2-4 turns; 10 leaves plenty of head-room while
# preventing a runaway handler.
MAX_AGENT_TURNS: int = 10


# Per-thread async locks, lazily created. asyncio.Lock is the right
# primitive here because every dispatcher run is already on the event
# loop.
_LOCKS: Dict[str, asyncio.Lock] = {}
_LOCK_REGISTRY_LOCK = asyncio.Lock()


async def _get_thread_lock(thread_id: str) -> asyncio.Lock:
    """Return (creating if needed) the async lock for ``thread_id``."""
    async with _LOCK_REGISTRY_LOCK:
        lock = _LOCKS.get(thread_id)
        if lock is None:
            lock = asyncio.Lock()
            _LOCKS[thread_id] = lock
        return lock


# ── Auto-advance hook ───────────────────────────────────────────────────────
#
# The dispatcher calls this after a successful auto-resolve. In prod we
# wire it up to re-run the parked pipeline stage for this order. In
# tests we replace it with a capture. The default is a no-op so unit
# tests don't need any wiring.

AutoAdvanceHook = Any  # async callable: (tenant_id, order_id) -> None


async def _default_auto_advance(tenant_id: str, order_id: str) -> None:
    logger.info(
        "HITL auto-advance (stub): tenant=%s order=%s — wire "
        "set_auto_advance_hook() to actually re-run the pipeline.",
        tenant_id, order_id,
    )


_auto_advance: AutoAdvanceHook = _default_auto_advance


def set_auto_advance_hook(fn: Optional[AutoAdvanceHook]) -> None:
    """Install (or reset) the auto-advance hook. Call from app lifespan."""
    global _auto_advance
    _auto_advance = fn or _default_auto_advance


def get_auto_advance_hook() -> AutoAdvanceHook:
    return _auto_advance


# ── Entrypoint ──────────────────────────────────────────────────────────────


_BACKGROUND_DISPATCHES: "set[asyncio.Task]" = set()

# Pytest detection — tests monkeypatch ``async_session_factory`` to point
# at an in-memory SQLite engine using ``StaticPool`` (one connection).
# Firing a fire-and-forget dispatch task then races with the session the
# HTTP handler is still refreshing and trips
# ``InvalidRequestError: Could not refresh instance`` in SQLAlchemy.
# Tests that want to exercise the dispatcher call
# ``dispatch_on_human_message`` directly (see test_chat_dispatcher.py),
# so skipping the fire-and-forget branch when pytest is loaded is safe.
_UNDER_PYTEST: bool = bool(sys.modules.get("pytest"))


def schedule_dispatch(thread_id: str, tenant_id: str) -> None:
    """Fire-and-forget wrapper used by the resolver.

    We wrap :func:`dispatch_on_human_message` in ``asyncio.create_task``
    so the HTTP call that triggered the human message doesn't block on
    the LLM round-trip. Exceptions inside the task are swallowed +
    logged — they shouldn't be able to kill the dispatcher loop.

    IMPORTANT: we keep a strong reference to each task in
    ``_BACKGROUND_DISPATCHES`` until it finishes. Without this, asyncio
    GCs unreferenced tasks before they run — which silently dropped
    every LLM reply on human-typed messages (HiTL thread stayed
    "not responding" because the dispatch task was evicted).
    """
    if _UNDER_PYTEST:
        return
    try:
        task = asyncio.create_task(
            dispatch_on_human_message(thread_id, tenant_id),
            name=f"hitl_chat_dispatch:{thread_id}",
        )
    except RuntimeError:
        # No running loop — likely a sync test harness. Just log and
        # move on; the test can drive dispatch_on_human_message
        # directly if it cares.
        logger.debug(
            "HITL chat dispatcher: no running loop, skipping schedule "
            "for thread %s (likely a sync test context)",
            thread_id,
        )
        return

    _BACKGROUND_DISPATCHES.add(task)

    def _finalize(t: "asyncio.Task") -> None:
        _BACKGROUND_DISPATCHES.discard(t)
        if t.cancelled():
            return
        exc = t.exception()
        if exc is not None:
            logger.warning(
                "HITL chat dispatch task raised for thread %s: %s",
                thread_id, exc,
            )

    task.add_done_callback(_finalize)


async def dispatch_on_human_message(
    thread_id: str, tenant_id: str,
) -> Optional[ChatReply]:
    """Run one agent-reply turn for a thread.

    Returns the :class:`ChatReply` produced (or ``None`` if no handler
    ran, e.g. the thread was terminal or capped out). Callers normally
    ignore the return value — it's exposed for tests.
    """
    lock = await _get_thread_lock(thread_id)
    async with lock:
        return await _dispatch_locked(thread_id, tenant_id)


async def _dispatch_locked(
    thread_id: str, tenant_id: str,
) -> Optional[ChatReply]:
    async with _session_mod.async_session_factory() as db:
        ctx = await _build_chat_context(db, thread_id, tenant_id)
        if ctx is None:
            # Thread is gone, not ours, or terminal.
            return None

        if _count_agent_turns(ctx) >= MAX_AGENT_TURNS:
            logger.warning(
                "HITL chat: thread %s hit MAX_AGENT_TURNS (%d) — escalating.",
                thread_id, MAX_AGENT_TURNS,
            )
            await _post_system_message(
                db, thread_id=thread_id, tenant_id=tenant_id,
                content=(
                    "I've replied too many times without resolving this. "
                    "Please click **Resolve** once you've fixed the "
                    "underlying data, or **Escalate** to hand this off."
                ),
                context={"action": "chat_turn_cap"},
            )
            return None

        handler = get_chat_handler(ctx.agent_id)
        if handler is None:
            logger.info(
                "HITL chat: no handler registered for agent_id=%r — "
                "posting a boilerplate reply.", ctx.agent_id,
            )
            await _post_system_message(
                db, thread_id=thread_id, tenant_id=tenant_id,
                content=(
                    f"I don't have a chat handler wired up for "
                    f"`{ctx.agent_id}` yet. Your message was recorded — "
                    "please resolve manually once you've fixed the block."
                ),
                context={"action": "no_handler", "agent_id": ctx.agent_id},
            )
            return None

    # Call the LLM outside the DB session so a slow completion doesn't
    # hold a connection. The handler is stateless w.r.t. the DB.
    # Publish a ``typing`` event so the UI can render an "agent is
    # thinking…" indicator while we wait for the completion.
    await _publish_typing(thread_id, state="start", agent_id=ctx.agent_id)
    try:
        reply = await _respond_with_tools(handler, ctx, tenant_id=tenant_id)
    finally:
        await _publish_typing(thread_id, state="stop", agent_id=ctx.agent_id)

    async with _session_mod.async_session_factory() as db:
        # Re-load thread inside a fresh session for the write phase. If
        # the operator / admin closed the thread while we were waiting
        # on the LLM, bail quietly.
        thread = await _reload_thread(db, thread_id, tenant_id)
        if thread is None or thread.status in {"RESOLVED", "ESCALATED"}:
            logger.debug(
                "HITL chat: thread %s went terminal during LLM call — "
                "dropping agent reply.", thread_id,
            )
            return reply

        # 1. Apply any proposed item.data patches.
        if reply.has_patches:
            await _apply_patches_to_item(
                db,
                tenant_id=tenant_id,
                order_id=ctx.order_id,
                item_no=ctx.item_no,
                patches=reply.patches,
            )

        # 2. Persist the agent's message. Goes through the resolver so
        # WS subscribers see it, but sender_type=agent so the resolver
        # won't re-dispatch (that's gated on sender_type=human).
        from labelforge.services.hitl.resolver import (
            AddMessageRequest,
            get_thread_resolver,
        )
        resolver = get_thread_resolver()
        await resolver.add_message(
            db,
            AddMessageRequest(
                tenant_id=tenant_id,
                thread_id=thread_id,
                sender_type="agent",
                content=reply.text,
                context={
                    "model": reply.model,
                    "cost_usd": reply.cost_usd,
                    "patches_applied": reply.patches or None,
                    "resolved": reply.resolved,
                },
                actor=ctx.agent_id,
            ),
        )

        # 3. If the handler signalled resolved, auto-close + auto-advance.
        if reply.resolved:
            try:
                await resolver.resolve_thread(
                    db,
                    tenant_id=tenant_id,
                    thread_id=thread_id,
                    actor=ctx.agent_id,
                    resolution_note=(
                        "Auto-resolved by chat: "
                        + (reply.text.splitlines()[0] if reply.text else "ok")
                    )[:500],
                )
            except Exception as exc:  # pragma: no cover
                logger.warning(
                    "HITL chat: auto-resolve failed for %s: %s",
                    thread_id, exc,
                )

            # Auto-advance is best-effort; failures are logged but
            # don't clobber the resolved state.
            try:
                await _auto_advance(tenant_id, ctx.order_id)
            except Exception as exc:  # pragma: no cover
                logger.warning(
                    "HITL chat: auto-advance hook failed for order %s: %s",
                    ctx.order_id, exc,
                )

    return reply


# ── Tool-use loop ───────────────────────────────────────────────────────────


# Hard cap on tool-call rounds per human message. Well above the
# 2-3 turns any realistic query should need, low enough that a
# misbehaving LLM can't burn tokens forever.
_MAX_TOOL_ROUNDS = 3


async def _respond_with_tools(
    handler,  # AgentChatHandler — avoid circular import
    ctx,      # ChatContext
    *,
    tenant_id: str,
):
    """Drive the LLM through up to ``_MAX_TOOL_ROUNDS`` tool-use rounds.

    Each round:
    - ask the handler for a reply against the current message history
    - if it requested one or more tools, execute them, append synthetic
      ``system`` messages with the results, and loop
    - if it did not, return the reply straight to the caller

    The final :class:`ChatReply` is what gets persisted as the visible
    agent message. Intermediate tool round-trips are invisible to the
    operator — only the concluding answer lands on the thread.
    """
    from labelforge.agents.chat import ChatMessage
    from labelforge.services.hitl.chat_tools import (
        ToolContext,
        resolve_importer_id_for_order,
        run_tool,
    )

    # Build the bound tool context ONCE — importer_id is looked up from
    # the order, never from LLM-supplied args.
    async with _session_mod.async_session_factory() as db:
        importer_id = await resolve_importer_id_for_order(
            db, tenant_id=tenant_id, order_id=ctx.order_id,
        )

    # Local mutable copy of the history so tool-results are visible to
    # the next handler.respond() call. We never persist these synthetic
    # messages to the DB — they only live for the duration of this turn.
    working_messages = list(ctx.messages)

    for round_idx in range(_MAX_TOOL_ROUNDS):
        working_ctx = _replace_messages(ctx, working_messages)
        reply = await handler.respond(working_ctx)
        if not reply.has_tool_calls:
            return reply

        tool_results: list[dict] = []
        async with _session_mod.async_session_factory() as db:
            tool_ctx = ToolContext(
                db=db,
                tenant_id=tenant_id,
                order_id=ctx.order_id,
                importer_id=importer_id,
                item_no=ctx.item_no,
            )
            for call in reply.tool_calls:
                name = str(call.get("name") or "")
                args = call.get("args") if isinstance(call.get("args"), dict) else {}
                result = await run_tool(tool_ctx, name, args)
                tool_results.append({"name": name, "args": args, "result": result})

        # Serialize each result into a system message the next turn can
        # read. We keep each result bounded so a poorly chosen tool call
        # (e.g. a 100-rule list) can't blow the context window.
        for tr in tool_results:
            rendered = _render_tool_result(tr)
            working_messages.append(ChatMessage(
                role="system",
                content=rendered,
                context={"tool_result": tr["name"]},
            ))

        logger.info(
            "HITL chat: round %d for thread %s executed %d tool(s): %s",
            round_idx + 1,
            ctx.thread_id,
            len(tool_results),
            [tr["name"] for tr in tool_results],
        )

    # Fell off the end of the loop — return whatever the last turn
    # produced, without tool_calls so the dispatcher persists it.
    working_ctx = _replace_messages(ctx, working_messages)
    final = await handler.respond(working_ctx)
    # Clear tool_calls on the final reply so the caller doesn't loop again.
    final.tool_calls = []
    return final


def _replace_messages(ctx, messages):
    """Return a ChatContext with the message list swapped — used inside
    the tool loop so we don't mutate the dispatcher's original ctx."""
    from labelforge.agents.chat import ChatContext
    return ChatContext(
        thread_id=ctx.thread_id,
        tenant_id=ctx.tenant_id,
        order_id=ctx.order_id,
        item_no=ctx.item_no,
        agent_id=ctx.agent_id,
        pause_context=ctx.pause_context,
        item_data=ctx.item_data,
        messages=messages,
        importer_profile=ctx.importer_profile,
        rules_summary=ctx.rules_summary,
        warnings_summary=ctx.warnings_summary,
        documents_summary=ctx.documents_summary,
        onboarding_summary=ctx.onboarding_summary,
        sibling_items=ctx.sibling_items,
    )


# Per-tool-result payload cap. Big enough to carry a 3KB doc-text
# extract, small enough that three rounds can't overflow.
_TOOL_RESULT_CHAR_CAP = 4000


def _render_tool_result(tr: dict) -> str:
    """Format a tool invocation + result as a system message."""
    import json as _json
    name = tr.get("name") or "?"
    try:
        serialised = _json.dumps(tr.get("result"), default=str, ensure_ascii=False)
    except (TypeError, ValueError):
        serialised = repr(tr.get("result"))
    if len(serialised) > _TOOL_RESULT_CHAR_CAP:
        serialised = (
            serialised[: _TOOL_RESULT_CHAR_CAP]
            + f"... [truncated at {_TOOL_RESULT_CHAR_CAP} chars]"
        )
    return f"[tool_result:{name}] {serialised}"


# ── Context building ────────────────────────────────────────────────────────


async def _build_chat_context(
    db: AsyncSession, thread_id: str, tenant_id: str,
) -> Optional[ChatContext]:
    """Load the thread, messages, and item.data into a :class:`ChatContext`.

    Returns ``None`` if the thread is missing, cross-tenant, or already
    in a terminal state.
    """
    result = await db.execute(
        select(HiTLThreadModel)
        .options(selectinload(HiTLThreadModel.messages))
        .where(
            HiTLThreadModel.id == thread_id,
            HiTLThreadModel.tenant_id == tenant_id,
        )
    )
    thread = result.scalar_one_or_none()
    if thread is None:
        return None
    if thread.status in {"RESOLVED", "ESCALATED"}:
        return None

    # Item is optional — order-level threads exist too (though the
    # advance-pipeline path always has item_no).
    item_data: Mapping[str, Any] = {}
    if thread.order_id and thread.item_no:
        item_result = await db.execute(
            select(OrderItemModel).where(
                OrderItemModel.order_id == thread.order_id,
                OrderItemModel.item_no == thread.item_no,
                OrderItemModel.tenant_id == tenant_id,
            )
        )
        item = item_result.scalar_one_or_none()
        if item is not None:
            item_data = dict(item.data or {})

    messages = [
        ChatMessage(role=m.sender_type, content=m.content, context=m.context)
        for m in sorted(thread.messages, key=lambda m: m.created_at or 0)
    ]

    # Pause context comes from the agent-message that opened the thread —
    # that's where _ensure_hitl_thread stores {stage, activity, reason, ...}.
    pause_context: Dict[str, Any] = {}
    first_agent = next((m for m in messages if m.role == "agent"), None)
    if first_agent and first_agent.context:
        pause_context.update(dict(first_agent.context))
    # Augment with item-level breadcrumbs the pipeline writes.
    for key in ("blocked_at_stage", "blocked_reason", "last_successful_state"):
        if key in item_data:
            pause_context.setdefault(key, item_data[key])

    # Static prefetch — every chat turn gets a bounded tenant summary so
    # the LLM can answer simple "what do we know?" questions without a
    # tool roundtrip. Heavier data (document bodies, full rule logic)
    # still flows through the :mod:`chat_tools` loop.
    (
        importer_profile, rules_summary, warnings_summary,
        documents_summary, onboarding_summary, sibling_items,
    ) = await _load_static_chat_context(
        db=db,
        tenant_id=tenant_id,
        order_id=thread.order_id,
        item_no=thread.item_no or "",
    )

    return ChatContext(
        thread_id=thread.id,
        tenant_id=tenant_id,
        order_id=thread.order_id,
        item_no=thread.item_no or "",
        agent_id=thread.agent_id,
        pause_context=pause_context,
        item_data=item_data,
        messages=messages,
        importer_profile=importer_profile,
        rules_summary=rules_summary,
        warnings_summary=warnings_summary,
        documents_summary=documents_summary,
        onboarding_summary=onboarding_summary,
        sibling_items=sibling_items,
    )


async def _load_static_chat_context(
    *, db: AsyncSession, tenant_id: str, order_id: str, item_no: str,
) -> tuple[
    Optional[Dict[str, Any]],
    List[Dict[str, Any]],
    List[Dict[str, Any]],
    List[Dict[str, Any]],
    Optional[Dict[str, Any]],
    List[Dict[str, Any]],
]:
    """Assemble the bounded-cost tenant summary used by every chat turn.

    Each block is capped so the resulting prompt never balloons past a
    few KB even when a tenant has hundreds of rules or docs. Full rows
    are reachable via the chat-tools registry.
    """
    from labelforge.db.models import (
        ComplianceRule,
        ImporterDocument,
        ImporterOnboardingSession,
        ImporterProfileModel,
        Order,
        OrderItemModel,
        WarningLabel,
    )

    _RULES_SUMMARY_CAP = 30
    _WARNINGS_SUMMARY_CAP = 15
    _DOCS_SUMMARY_CAP = 40

    # 1. Order → importer_id.
    order_row = (await db.execute(
        select(Order).where(
            Order.id == order_id,
            Order.tenant_id == tenant_id,
        )
    )).scalar_one_or_none()
    importer_id = order_row.importer_id if order_row is not None else None

    # 2. Latest importer profile.
    importer_profile: Optional[Dict[str, Any]] = None
    if importer_id:
        prof = (await db.execute(
            select(ImporterProfileModel)
            .where(
                ImporterProfileModel.importer_id == importer_id,
                ImporterProfileModel.tenant_id == tenant_id,
            )
            .order_by(ImporterProfileModel.version.desc())
            .limit(1)
        )).scalar_one_or_none()
        if prof is not None:
            importer_profile = {
                "name": order_row.importer_id if order_row is not None else None,
                "version": prof.version,
                "brand_treatment": prof.brand_treatment or {},
                "panel_layouts": prof.panel_layouts or {},
                "handling_symbol_rules": prof.handling_symbol_rules or {},
                "logo_asset_hash": prof.logo_asset_hash,
            }

    # 3. Compliance rules (cap summary count).
    rule_rows = (await db.execute(
        select(ComplianceRule)
        .where(
            ComplianceRule.tenant_id == tenant_id,
            ComplianceRule.is_active == True,  # noqa: E712
        )
        .limit(_RULES_SUMMARY_CAP)
    )).scalars().all()
    rules_summary = [
        {
            "rule_code": r.rule_code,
            "title": (r.title or "")[:120],
            "region": r.region,
        }
        for r in rule_rows
    ]

    # 4. Warning labels (cap summary count).
    warning_rows = (await db.execute(
        select(WarningLabel)
        .where(
            WarningLabel.tenant_id == tenant_id,
            WarningLabel.is_active == True,  # noqa: E712
        )
        .limit(_WARNINGS_SUMMARY_CAP)
    )).scalars().all()
    warnings_summary = [
        {
            "code": w.code,
            "title": (w.title or "")[:120],
            "region": w.region,
        }
        for w in warning_rows
    ]

    # 5. Uploaded documents (metadata only — no blob fetch).
    documents_summary: List[Dict[str, Any]] = []
    if importer_id:
        doc_rows = (await db.execute(
            select(ImporterDocument)
            .where(
                ImporterDocument.importer_id == importer_id,
                ImporterDocument.tenant_id == tenant_id,
            )
            .limit(_DOCS_SUMMARY_CAP)
        )).scalars().all()
        documents_summary = [
            {
                "id": d.id,
                "doc_type": d.doc_type,
                "filename": d.filename,
                "size_bytes": d.size_bytes,
                "content_hash": d.content_hash,
            }
            for d in doc_rows
        ]

    # 6. Onboarding session — status + keys only (no full extracted_values).
    onboarding_summary: Optional[Dict[str, Any]] = None
    if importer_id:
        sess = (await db.execute(
            select(ImporterOnboardingSession)
            .where(
                ImporterOnboardingSession.importer_id == importer_id,
                ImporterOnboardingSession.tenant_id == tenant_id,
            )
            .order_by(ImporterOnboardingSession.started_at.desc())
            .limit(1)
        )).scalar_one_or_none()
        if sess is not None:
            ev = sess.extracted_values or {}
            agents_state = sess.agents_state or {}
            extracted_keys = sorted(list(ev.keys())) if isinstance(ev, dict) else []
            onboarding_summary = {
                "session_id": sess.id,
                "status": sess.status,
                "agents": {
                    k: (v.get("status") if isinstance(v, dict) else str(v))
                    for k, v in agents_state.items()
                } if isinstance(agents_state, dict) else {},
                "extracted_keys": extracted_keys,
            }

    # 7. Sibling items on the same order.
    sibling_items: List[Dict[str, Any]] = []
    if order_id:
        sib_rows = (await db.execute(
            select(OrderItemModel)
            .where(
                OrderItemModel.order_id == order_id,
                OrderItemModel.tenant_id == tenant_id,
            )
        )).scalars().all()
        sibling_items = [
            {"item_no": r.item_no, "state": r.state}
            for r in sib_rows
            if r.item_no != item_no
        ]

    return (
        importer_profile,
        rules_summary,
        warnings_summary,
        documents_summary,
        onboarding_summary,
        sibling_items,
    )


async def _reload_thread(
    db: AsyncSession, thread_id: str, tenant_id: str,
) -> Optional[HiTLThreadModel]:
    result = await db.execute(
        select(HiTLThreadModel).where(
            HiTLThreadModel.id == thread_id,
            HiTLThreadModel.tenant_id == tenant_id,
        )
    )
    return result.scalar_one_or_none()


def _count_agent_turns(ctx: ChatContext) -> int:
    return sum(1 for m in ctx.messages if m.role == "agent")


# ── Item-data patching ──────────────────────────────────────────────────────


async def _apply_patches_to_item(
    db: AsyncSession,
    *,
    tenant_id: str,
    order_id: str,
    item_no: str,
    patches: Mapping[str, Any],
) -> None:
    """Shallow-merge ``patches`` into ``item.data`` and commit.

    Nested keys (``"fused.upc"``) are split on ``.`` and applied as
    nested dict-writes so a chat handler can update a specific subtree
    without clobbering the rest of the blob.
    """
    if not patches:
        return
    result = await db.execute(
        select(OrderItemModel).where(
            OrderItemModel.order_id == order_id,
            OrderItemModel.item_no == item_no,
            OrderItemModel.tenant_id == tenant_id,
        )
    )
    item = result.scalar_one_or_none()
    if item is None:
        logger.warning(
            "HITL chat: patch requested for missing item order=%s item_no=%s",
            order_id, item_no,
        )
        return

    data = dict(item.data or {})
    for key, value in patches.items():
        _nested_set(data, key, value)
    # Clear the block markers so the next advance doesn't re-raise the
    # same HITL on the same inputs.
    data.pop("blocked_reason", None)
    item.data = data
    await db.commit()


def _nested_set(d: Dict[str, Any], dotted_key: str, value: Any) -> None:
    """Set ``d[a][b][c] = value`` for a dotted key ``"a.b.c"``.

    Creates intermediate dicts as needed. Non-dict intermediates are
    overwritten (a chat patch "win" is intentional — if the operator
    and the LLM agreed on a change, it should stick).
    """
    parts = dotted_key.split(".")
    cursor: Dict[str, Any] = d
    for part in parts[:-1]:
        nxt = cursor.get(part)
        if not isinstance(nxt, dict):
            nxt = {}
            cursor[part] = nxt
        cursor = nxt
    cursor[parts[-1]] = value


# ── Typing events ───────────────────────────────────────────────────────────


async def _publish_typing(
    thread_id: str, *, state: str, agent_id: str,
) -> None:
    """Publish a ``typing`` envelope so the live UI can render an indicator.

    ``state`` is one of ``"start"`` / ``"stop"`` — the frontend flips its
    "agent is thinking…" bubble on/off accordingly. Failures are logged
    and swallowed; a missing typing indicator shouldn't block the reply.
    """
    try:
        from labelforge.services.hitl.router import (
            EventType,
            get_message_router,
            make_envelope,
        )
        await get_message_router().publish(
            thread_id,
            make_envelope(
                EventType.TYPING,
                thread_id,
                {"role": "agent", "agent_id": agent_id, "state": state},
            ),
        )
    except Exception as exc:  # pragma: no cover — defensive
        logger.debug(
            "HITL chat: typing %s publish failed for %s: %s",
            state, thread_id, exc,
        )


# ── System messages (for error / cap paths) ─────────────────────────────────


async def _post_system_message(
    db: AsyncSession,
    *,
    thread_id: str,
    tenant_id: str,
    content: str,
    context: Optional[Mapping[str, Any]] = None,
) -> None:
    """Post a ``system`` message directly, skipping the resolver hook.

    We go direct-to-DB here because we don't want these utility
    messages to flip the thread's OPEN → IN_PROGRESS state or trip
    other lifecycle side effects.
    """
    from uuid import uuid4

    msg = HiTLMessageModel(
        id=str(uuid4()),
        thread_id=thread_id,
        tenant_id=tenant_id,
        sender_type="system",
        content=content,
        context=dict(context) if context else None,
    )
    db.add(msg)
    await db.commit()

    # Still broadcast so the live UI sees it.
    from labelforge.services.hitl.router import (
        EventType,
        get_message_router,
        make_envelope,
    )
    await get_message_router().publish(
        thread_id,
        make_envelope(
            EventType.AGENT_MESSAGE,  # render as an agent bubble
            thread_id,
            {
                "message_id": msg.id,
                "sender_type": "system",
                "content": content,
                "context": dict(context) if context else None,
            },
        ),
    )


__all__ = [
    "MAX_AGENT_TURNS",
    "dispatch_on_human_message",
    "get_auto_advance_hook",
    "schedule_dispatch",
    "set_auto_advance_hook",
]
