"""HiTL chat tool registry.

The chat handler (:mod:`labelforge.agents.chat`) is LLM-backed but
text-only — the LLM can't call functions natively. Instead, when it
wants extra data (a document's body, a rule's logic, a sibling item),
it emits a fenced-JSON ``tools`` array at the end of its reply. The
chat dispatcher parses that, calls into this registry, and appends the
results to the conversation before re-invoking the handler.

All tools here are **tenant-scoped** — the :class:`ToolContext` is
constructed by the dispatcher from the authenticated thread context,
not from the LLM's input. The LLM may supply filter args (``region``,
``agent``, ``document_id``, …) but cannot cross a tenant boundary.

See :func:`run_tool` for the single entry point the dispatcher uses.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Awaitable, Callable, Dict, List, Mapping, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from labelforge.core.doc_extract import extract_text
from labelforge.db.models import (
    ComplianceRule,
    ImporterDocument,
    ImporterOnboardingSession,
    ImporterProfileModel,
    Order,
    OrderItemModel,
    WarningLabel,
)

logger = logging.getLogger(__name__)

# Token-budget guards. Individual tools clamp their own limits; the caller
# may further trim before injecting into the next prompt turn.
_DOC_TEXT_DEFAULT_MAX = 3000
_DOC_TEXT_HARD_CAP = 8000
_DOC_SNIPPET_CHARS = 240
_SEARCH_DEFAULT_LIMIT = 3
_SEARCH_HARD_CAP = 10
_RULE_LIST_CAP = 200
_WARNING_LIST_CAP = 100


@dataclass(frozen=True)
class ToolContext:
    """Bound scope every tool runs against — never user-supplied."""
    db: AsyncSession
    tenant_id: str
    order_id: str
    importer_id: Optional[str]
    item_no: str


ToolHandler = Callable[[ToolContext, Mapping[str, Any]], Awaitable[Any]]


# ── Individual tools ────────────────────────────────────────────────────────


async def _tool_get_importer_profile(
    ctx: ToolContext, args: Mapping[str, Any],
) -> Dict[str, Any]:
    if not ctx.importer_id:
        return {"error": "no importer_id bound to this order"}
    prof = (await ctx.db.execute(
        select(ImporterProfileModel)
        .where(
            ImporterProfileModel.importer_id == ctx.importer_id,
            ImporterProfileModel.tenant_id == ctx.tenant_id,
        )
        .order_by(ImporterProfileModel.version.desc())
        .limit(1)
    )).scalar_one_or_none()
    if prof is None:
        return {"error": "no profile rows — onboarding not finalized"}
    return {
        "version": prof.version,
        "brand_treatment": prof.brand_treatment or {},
        "panel_layouts": prof.panel_layouts or {},
        "handling_symbol_rules": prof.handling_symbol_rules or {},
        "pi_template_mapping": prof.pi_template_mapping or {},
        "logo_asset_hash": prof.logo_asset_hash,
    }


async def _tool_list_compliance_rules(
    ctx: ToolContext, args: Mapping[str, Any],
) -> List[Dict[str, Any]]:
    stmt = (
        select(ComplianceRule)
        .where(
            ComplianceRule.tenant_id == ctx.tenant_id,
            ComplianceRule.is_active == True,  # noqa: E712
        )
        .limit(_RULE_LIST_CAP)
    )
    region = args.get("region")
    if isinstance(region, str) and region:
        stmt = stmt.where(ComplianceRule.region == region)
    rows = (await ctx.db.execute(stmt)).scalars().all()
    out: List[Dict[str, Any]] = []
    for r in rows:
        logic = r.logic or {}
        # Only expose top-level structure so a large rule doesn't blow
        # the context window — the LLM can request a specific rule by
        # code via a follow-up tool call if it needs the full logic.
        if isinstance(logic, Mapping):
            logic_keys = sorted(logic.keys())
        else:
            logic_keys = []
        out.append({
            "rule_code": r.rule_code,
            "version": r.version,
            "title": r.title,
            "region": r.region,
            "placement": r.placement,
            "logic_keys": logic_keys,
            "logic": logic,
        })
    return out


async def _tool_list_warning_labels(
    ctx: ToolContext, args: Mapping[str, Any],
) -> List[Dict[str, Any]]:
    stmt = (
        select(WarningLabel)
        .where(
            WarningLabel.tenant_id == ctx.tenant_id,
            WarningLabel.is_active == True,  # noqa: E712
        )
        .limit(_WARNING_LIST_CAP)
    )
    region = args.get("region")
    if isinstance(region, str) and region:
        stmt = stmt.where(WarningLabel.region == region)
    rows = (await ctx.db.execute(stmt)).scalars().all()
    return [
        {
            "code": w.code,
            "title": w.title,
            "text_en": (w.text_en or "")[:500],
            "region": w.region,
            "placement": w.placement,
        }
        for w in rows
    ]


async def _tool_list_importer_documents(
    ctx: ToolContext, args: Mapping[str, Any],
) -> List[Dict[str, Any]]:
    if not ctx.importer_id:
        return []
    rows = (await ctx.db.execute(
        select(ImporterDocument).where(
            ImporterDocument.importer_id == ctx.importer_id,
            ImporterDocument.tenant_id == ctx.tenant_id,
        )
    )).scalars().all()
    return [
        {
            "id": d.id,
            "doc_type": d.doc_type,
            "filename": d.filename,
            "size_bytes": d.size_bytes,
            "content_hash": d.content_hash,
            "version": d.version,
        }
        for d in rows
    ]


async def _tool_get_document_text(
    ctx: ToolContext, args: Mapping[str, Any],
) -> Dict[str, Any]:
    doc_id = args.get("document_id")
    if not isinstance(doc_id, str) or not doc_id:
        return {"error": "document_id (str) required"}
    try:
        max_chars = int(args.get("max_chars") or _DOC_TEXT_DEFAULT_MAX)
    except (TypeError, ValueError):
        max_chars = _DOC_TEXT_DEFAULT_MAX
    max_chars = max(200, min(_DOC_TEXT_HARD_CAP, max_chars))

    doc = (await ctx.db.execute(
        select(ImporterDocument).where(
            ImporterDocument.id == doc_id,
            ImporterDocument.tenant_id == ctx.tenant_id,
        )
    )).scalar_one_or_none()
    if doc is None:
        return {"error": f"document {doc_id!r} not found for this tenant"}
    # Cross-check the importer too so a chat scoped to order A can't read
    # docs belonging to importer B (same tenant, different importer).
    if ctx.importer_id and doc.importer_id != ctx.importer_id:
        return {"error": f"document {doc_id!r} belongs to a different importer"}

    from labelforge.api.v1.documents import get_blob_store  # local import — avoids cycle
    store = get_blob_store()
    try:
        blob = await store.download(doc.s3_key)
    except (FileNotFoundError, KeyError):
        return {"error": f"blob missing for {doc_id}", "s3_key": doc.s3_key}
    text = extract_text(blob, doc.filename)
    truncated = len(text) > max_chars
    return {
        "document_id": doc.id,
        "filename": doc.filename,
        "doc_type": doc.doc_type,
        "text": text[:max_chars],
        "truncated": truncated,
        "full_length": len(text),
    }


async def _tool_search_documents(
    ctx: ToolContext, args: Mapping[str, Any],
) -> List[Dict[str, Any]]:
    if not ctx.importer_id:
        return []
    query = args.get("query")
    if not isinstance(query, str) or not query.strip():
        return [{"error": "query (str) required"}]
    try:
        limit = int(args.get("limit") or _SEARCH_DEFAULT_LIMIT)
    except (TypeError, ValueError):
        limit = _SEARCH_DEFAULT_LIMIT
    limit = max(1, min(_SEARCH_HARD_CAP, limit))

    from labelforge.api.v1.documents import get_blob_store
    store = get_blob_store()
    q_lower = query.lower().strip()

    rows = (await ctx.db.execute(
        select(ImporterDocument).where(
            ImporterDocument.importer_id == ctx.importer_id,
            ImporterDocument.tenant_id == ctx.tenant_id,
        )
    )).scalars().all()

    hits: List[Dict[str, Any]] = []
    for d in rows:
        # Filename-level match is cheap and always safe.
        if q_lower in d.filename.lower() or q_lower in (d.doc_type or "").lower():
            hits.append({
                "id": d.id,
                "filename": d.filename,
                "doc_type": d.doc_type,
                "snippet": None,
                "matched": "filename",
            })
            if len(hits) >= limit:
                return hits

    # Fall through to body scans only for non-image blobs and only until
    # we hit the limit — this is not a search index, just a small-n loop.
    for d in rows:
        if any(h["id"] == d.id for h in hits):
            continue
        if any(d.filename.lower().endswith(ext) for ext in (".jpg", ".jpeg", ".png", ".gif")):
            continue
        try:
            blob = await store.download(d.s3_key)
        except Exception:  # pragma: no cover
            continue
        body = extract_text(blob, d.filename) or ""
        idx = body.lower().find(q_lower)
        if idx == -1:
            continue
        start = max(0, idx - _DOC_SNIPPET_CHARS // 2)
        end = min(len(body), idx + _DOC_SNIPPET_CHARS // 2)
        hits.append({
            "id": d.id,
            "filename": d.filename,
            "doc_type": d.doc_type,
            "snippet": body[start:end],
            "matched": "body",
        })
        if len(hits) >= limit:
            break
    return hits


async def _tool_get_onboarding_extraction(
    ctx: ToolContext, args: Mapping[str, Any],
) -> Dict[str, Any]:
    if not ctx.importer_id:
        return {"error": "no importer_id bound to this order"}
    sess = (await ctx.db.execute(
        select(ImporterOnboardingSession)
        .where(
            ImporterOnboardingSession.importer_id == ctx.importer_id,
            ImporterOnboardingSession.tenant_id == ctx.tenant_id,
        )
        .order_by(ImporterOnboardingSession.started_at.desc())
        .limit(1)
    )).scalar_one_or_none()
    if sess is None:
        return {"error": "no onboarding sessions for this importer"}

    payload: Dict[str, Any] = {
        "session_id": sess.id,
        "status": sess.status,
        "agents": sess.agents_state or {},
    }
    agent = args.get("agent")
    ev = sess.extracted_values or {}
    if isinstance(agent, str) and agent:
        payload["agent"] = agent
        payload["extracted_values"] = {agent: (ev.get(agent) if isinstance(ev, Mapping) else None)}
    else:
        payload["extracted_values"] = ev
    return payload


async def _tool_get_item_data(
    ctx: ToolContext, args: Mapping[str, Any],
) -> Dict[str, Any]:
    target = args.get("item_no")
    if not isinstance(target, str) or not target:
        return {"error": "item_no (str) required"}
    row = (await ctx.db.execute(
        select(OrderItemModel).where(
            OrderItemModel.order_id == ctx.order_id,
            OrderItemModel.tenant_id == ctx.tenant_id,
            OrderItemModel.item_no == target,
        )
    )).scalar_one_or_none()
    if row is None:
        return {"error": f"no item {target!r} on order {ctx.order_id}"}
    data = dict(row.data or {})
    # Strip the heavy payload keys that would blow the context window.
    for k in ("composed_artifacts", "die_cut_svg", "line_drawing_svg", "approval_pdf"):
        data.pop(k, None)
    return {
        "item_no": row.item_no,
        "state": row.state,
        "data": data,
    }


# ── Registry + dispatch ─────────────────────────────────────────────────────


_TOOLS: Dict[str, ToolHandler] = {
    "get_importer_profile": _tool_get_importer_profile,
    "list_compliance_rules": _tool_list_compliance_rules,
    "list_warning_labels": _tool_list_warning_labels,
    "list_importer_documents": _tool_list_importer_documents,
    "get_document_text": _tool_get_document_text,
    "search_documents": _tool_search_documents,
    "get_onboarding_extraction": _tool_get_onboarding_extraction,
    "get_item_data": _tool_get_item_data,
}


def available_tool_names() -> List[str]:
    """Used by tests + handlers that want to describe the catalog."""
    return sorted(_TOOLS.keys())


async def run_tool(
    ctx: ToolContext, name: str, args: Optional[Mapping[str, Any]] = None,
) -> Any:
    """Execute a single tool call. Unknown tools return an error dict
    instead of raising so the LLM gets a friendly signal back.
    """
    handler = _TOOLS.get(name)
    if handler is None:
        return {
            "error": f"unknown tool {name!r}",
            "available": available_tool_names(),
        }
    try:
        return await handler(ctx, args or {})
    except Exception as exc:  # pragma: no cover — defensive
        logger.exception("HITL chat tool %s failed: %s", name, exc)
        return {"error": f"{type(exc).__name__}: {exc}"}


async def resolve_importer_id_for_order(
    db: AsyncSession, tenant_id: str, order_id: str,
) -> Optional[str]:
    """Look up the importer_id bound to an order.

    The dispatcher uses this when building the :class:`ToolContext` so
    every tool is pre-scoped to the right importer.
    """
    row = (await db.execute(
        select(Order).where(
            Order.id == order_id,
            Order.tenant_id == tenant_id,
        )
    )).scalar_one_or_none()
    return row.importer_id if row is not None else None
