"""Auto-advance wiring for HITL chat auto-resolve.

When a chat handler signals ``resolved: true``, the dispatcher closes
the thread and then calls
:func:`labelforge.services.hitl.chat_dispatcher.get_auto_advance_hook()`
to give the order a shove forward. This module contains the production
implementation of that hook.

Design notes
------------
* We deliberately do NOT make an HTTP call back to our own
  ``/api/v1/orders/{id}/advance`` endpoint. That would require
  stamping an internal JWT, managing a client session, and tolerating
  self-call network flakiness — all for a call we can already make
  in-process.
* We also deliberately do NOT refactor :func:`advance_order_pipeline`
  into a thin wrapper around a reusable core. The handler has 200+
  lines of orchestration that shouldn't change for this feature, and
  a lift-and-extract refactor risks regressions in the one code path
  production actually depends on.
* Instead: we call the handler directly with a synthesized
  :class:`TokenPayload` for the tenant. FastAPI's ``Depends()``
  defaults are only consulted when the handler is invoked through
  the router; calling the underlying async function with explicit
  kwargs bypasses them.
"""
from __future__ import annotations

import logging
import time
from typing import Optional

from labelforge.core.auth import Capability, Role, TokenPayload
from labelforge.db import session as _session_mod

logger = logging.getLogger(__name__)


# Capabilities we mint onto the synthetic system token. The advance
# handler doesn't check capabilities itself, but any helper it calls
# downstream might — we scope to the OPS role's set so this token has
# exactly the rights a human operator would have.
_SYSTEM_CAPABILITIES = {
    Capability.ORDER_VIEW,
    Capability.ORDER_REPROCESS,
    Capability.ITEM_REPRODUCE,
}


def _system_token(tenant_id: str) -> TokenPayload:
    """Build a throwaway :class:`TokenPayload` for server-internal calls.

    The token is never signed or returned over the wire — it only
    flows through in-process function calls. ``exp`` is set an hour in
    the future so any future ``time.time()`` check passes.
    """
    return TokenPayload(
        user_id="system:hitl-auto-advance",
        tenant_id=tenant_id,
        role=Role.OPS,
        capabilities=set(_SYSTEM_CAPABILITIES),
        exp=time.time() + 3600,
    )


async def run_auto_advance(tenant_id: str, order_id: str) -> None:
    """Re-invoke the order-advance pipeline for ``order_id``.

    Best-effort: exceptions are logged and swallowed. The thread is
    already RESOLVED by the time this fires, so a failure here just
    means the operator has to click "Advance pipeline" themselves —
    the chat experience is still fine.
    """
    try:
        # Local imports: the orders module pulls in a big dependency
        # graph (FastAPI, the full workflow activities) that we don't
        # want to load at module import time.
        from labelforge.api.v1.orders import advance_order_pipeline
    except ImportError as exc:  # pragma: no cover
        logger.warning("auto-advance: cannot import advance_order_pipeline: %s", exc)
        return

    async with _session_mod.async_session_factory() as db:
        try:
            response = await advance_order_pipeline(
                order_id=order_id,
                _user=_system_token(tenant_id),
                db=db,
            )
        except Exception as exc:
            logger.warning(
                "auto-advance: advance_order_pipeline raised for "
                "tenant=%s order=%s: %s",
                tenant_id, order_id, exc,
            )
            return

        logger.info(
            "auto-advance: tenant=%s order=%s advanced=%s stalled=%r",
            tenant_id, order_id,
            getattr(response, "items_advanced", None) if response else None,
            getattr(response, "stalled_reason", None) if response else None,
        )


def install() -> None:
    """Install :func:`run_auto_advance` as the dispatcher's auto-advance hook.

    Call this from the app lifespan (``app.py`` startup) so the chat
    dispatcher can reach it. Safe to call multiple times — just
    re-registers the same function.
    """
    from labelforge.services.hitl.chat_dispatcher import set_auto_advance_hook

    set_auto_advance_hook(run_auto_advance)
    logger.info("HITL chat auto-advance hook installed")


__all__ = ["install", "run_auto_advance"]
