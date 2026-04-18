"""HITL chat handlers — per-agent conversational responder.

When an operator replies in a HITL thread, the chat dispatcher loads the
right handler (keyed by ``thread.agent_id``), feeds it the original pause
context plus the full message history, and posts whatever the handler
returns back to the thread as an ``agent_message``.

Handlers may also propose patches to ``item.data`` via tool-calls and
signal that the block is resolved (which auto-closes the thread + kicks
the pipeline-advance hook).

Tool-call protocol
------------------
Plain-text completions, no native function-calling. The handler asks the
LLM to terminate its reply with a single fenced JSON block::

    ```json
    {
      "patches": {"<field>": <value>, ...},   # optional
      "resolved": true|false                  # default false
    }
    ```

:func:`parse_tool_call` strips that block from the visible reply,
validates patches against the handler's allowlist, and returns a
:class:`ChatReply`.

Adding a new agent
------------------
Either subclass :class:`AgentChatHandler` and override the system-prompt
factory (the pattern most agents will use), or instantiate
:class:`GenericChatHandler` directly when the only thing that varies is
the prompt and the patch-allowlist. Register the handler in
``labelforge.agents.chat_handlers.__init__``.
"""
from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, field
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence

from labelforge.config import settings
from labelforge.core.llm import LLMProvider, OpenAIProvider

logger = logging.getLogger(__name__)


# ── Data shapes ─────────────────────────────────────────────────────────────


@dataclass
class ChatMessage:
    """One turn in the conversation, normalized for LLM consumption."""
    role: str  # "agent" | "human" | "system"
    content: str
    context: Optional[Mapping[str, Any]] = None


@dataclass
class ChatContext:
    """Everything the chat handler needs to answer a single human turn.

    The bottom-half fields are bounded summaries the chat dispatcher
    pre-loads on every turn so the LLM can answer most questions without
    any tool call at all. Heavier retrieval (document bodies, rule logic,
    full extracted payloads) goes through the tool-use loop in
    :meth:`AgentChatHandler.respond` / :mod:`labelforge.services.hitl.chat_tools`.
    """
    thread_id: str
    tenant_id: str
    order_id: str
    item_no: str
    agent_id: str
    pause_context: Mapping[str, Any]   # thread.context + item.data["blocked_*"]
    item_data: Mapping[str, Any]       # current item.data snapshot
    messages: Sequence[ChatMessage]    # full history, oldest first
    importer_profile: Optional[Mapping[str, Any]] = None

    # Static prefetch (loaded by _build_chat_context). Bounded + cheap.
    rules_summary: List[Mapping[str, Any]] = field(default_factory=list)
    warnings_summary: List[Mapping[str, Any]] = field(default_factory=list)
    documents_summary: List[Mapping[str, Any]] = field(default_factory=list)
    onboarding_summary: Optional[Mapping[str, Any]] = None
    sibling_items: List[Mapping[str, Any]] = field(default_factory=list)


@dataclass
class ChatReply:
    """What the handler decided to do."""
    text: str                                 # message_to_post (visible to operator)
    patches: Dict[str, Any] = field(default_factory=dict)
    resolved: bool = False
    cost_usd: float = 0.0
    model: str = ""
    # Tool calls the LLM requested this turn. When non-empty, the
    # dispatcher executes them, appends synthetic ``[tool_result:…]``
    # messages to the ChatContext, and re-invokes ``respond()`` without
    # persisting the visible text from this turn to the thread.
    tool_calls: List[Dict[str, Any]] = field(default_factory=list)

    @property
    def has_patches(self) -> bool:
        return bool(self.patches)

    @property
    def has_tool_calls(self) -> bool:
        return bool(self.tool_calls)


# ── LLM provider singleton (lazy) ───────────────────────────────────────────


_provider: Optional[LLMProvider] = None


def get_chat_provider() -> LLMProvider:
    """Return the LLM provider used for HITL chat. Lazy-init.

    Tests can override via :func:`set_chat_provider` (e.g. to install a
    StubProvider) without touching environment variables.
    """
    global _provider
    if _provider is None:
        if not settings.openai_api_key:
            raise RuntimeError(
                "OPENAI_API_KEY is not configured — HITL chat cannot reach the model. "
                "Set it in .env or call set_chat_provider() with a stub.",
            )
        _provider = OpenAIProvider(api_key=settings.openai_api_key)
    return _provider


def set_chat_provider(provider: Optional[LLMProvider]) -> None:
    """Install a custom LLM provider (or reset to default with ``None``)."""
    global _provider
    _provider = provider


# Default chat model. We pin a cheaper model than the workflow default so
# operator chats don't blow up the per-tenant budget. Override with the
# ``LLM_CHAT_MODEL`` env var if you want parity with the workflow model.
DEFAULT_CHAT_MODEL = "gpt-4o-mini"


# ── Tool-call parsing ───────────────────────────────────────────────────────


_FENCED_JSON_RE = re.compile(
    r"```(?:json)?\s*(\{.*?\})\s*```\s*\Z",
    re.DOTALL,
)


def parse_tool_call(raw: str) -> tuple[str, Dict[str, Any]]:
    """Split LLM output into ``(visible_text, tool_call_dict)``.

    Looks for a single fenced ```json {...}``` block at the END of the
    response. If found, strips it from the visible text and parses the
    JSON. Malformed JSON or a missing block returns an empty tool-call
    dict so the visible reply is preserved untouched.

    The "must be at end" anchor is intentional — agents sometimes include
    code-fenced examples mid-response, and we don't want those treated
    as tool calls.
    """
    if not raw:
        return "", {}
    match = _FENCED_JSON_RE.search(raw)
    if match is None:
        return raw.strip(), {}
    json_blob = match.group(1)
    try:
        parsed = json.loads(json_blob)
        if not isinstance(parsed, dict):
            logger.warning("HITL chat tool-call was not a JSON object: %r", parsed)
            return raw.strip(), {}
    except json.JSONDecodeError as exc:
        logger.warning("HITL chat tool-call JSON decode failed: %s", exc)
        return raw.strip(), {}
    visible = raw[: match.start()].rstrip()
    return visible, parsed


def filter_patches(
    proposed: Mapping[str, Any],
    allowlist: Iterable[str],
) -> tuple[Dict[str, Any], List[str]]:
    """Return ``(applied, dropped)`` after enforcing the allowlist.

    ``allowlist`` is a flat list of dotted-key prefixes — e.g.
    ``["country_of_origin", "fused.upc", "*"]``. Wildcard ``"*"`` allows
    everything; otherwise a key is allowed if any prefix matches.

    Keys that fail the allowlist land in ``dropped`` so the caller can
    surface them to the operator instead of silently swallowing them.
    """
    if not proposed:
        return {}, []
    allow = list(allowlist)
    if "*" in allow:
        return dict(proposed), []
    applied: Dict[str, Any] = {}
    dropped: List[str] = []
    for key, value in proposed.items():
        if any(key == prefix or key.startswith(prefix + ".") for prefix in allow):
            applied[key] = value
        else:
            dropped.append(key)
    return applied, dropped


# ── Base handler ────────────────────────────────────────────────────────────


class AgentChatHandler:
    """Base class for per-agent HITL chat responders.

    Subclasses customize:

    * :attr:`agent_id` — must match ``HiTLThreadModel.agent_id`` so the
      dispatcher can look the handler up.
    * :attr:`patch_allowlist` — keys in ``item.data`` this handler is
      allowed to mutate via tool-calls. Defaults to empty (chat-only).
    * :meth:`build_system_prompt` — called once per turn to produce the
      ``role: system`` opener for the LLM. The default builder includes
      the agent name, the pause reason, and the patch-allowlist.

    Most agents won't need anything beyond the defaults — see
    :class:`GenericChatHandler` for the zero-subclass usage pattern.
    """

    agent_id: str = "unknown"
    patch_allowlist: Sequence[str] = ()
    role_description: str = "an agent in the LabelForge pipeline"
    model: str = DEFAULT_CHAT_MODEL
    max_tokens: int = 800
    temperature: float = 0.2

    def __init__(self, *, provider: Optional[LLMProvider] = None) -> None:
        self._provider_override = provider

    # ── Public entrypoint ─────────────────────────────────────────────

    async def respond(self, ctx: ChatContext) -> ChatReply:
        """Produce an agent-side reply for the next turn of the chat."""
        provider = self._provider_override or get_chat_provider()
        messages = self._build_llm_messages(ctx)
        try:
            result = await provider.complete(
                model=self.model,
                messages=messages,
                max_tokens=self.max_tokens,
                temperature=self.temperature,
            )
        except Exception as exc:  # pragma: no cover — provider failures
            logger.exception("HITL chat LLM call failed: %s", exc)
            return ChatReply(
                text=(
                    "Sorry — I hit an error reaching my brain. "
                    "Please continue manually or try again in a moment."
                ),
                model=self.model,
            )
        visible, tool_call = parse_tool_call(result.content)
        applied, dropped = filter_patches(
            tool_call.get("patches") or {}, self.patch_allowlist,
        )
        if dropped:
            visible = (
                visible.rstrip()
                + "\n\n_(I tried to update fields I'm not authorized to change: "
                + ", ".join(sorted(dropped))
                + ".)_"
            )
        # Tool-use: the LLM can request data lookups via a "tools" array
        # in the same fenced JSON block. The dispatcher drives the loop —
        # here we only normalise + surface the raw request so it can be
        # validated by the registry.
        raw_tool_calls = tool_call.get("tools") or []
        normalised_tools: List[Dict[str, Any]] = []
        if isinstance(raw_tool_calls, list):
            for entry in raw_tool_calls:
                if isinstance(entry, dict) and isinstance(entry.get("name"), str):
                    normalised_tools.append({
                        "name": entry["name"],
                        "args": entry.get("args") or {},
                    })
        return ChatReply(
            text=visible or "(no reply)",
            patches=applied,
            resolved=bool(tool_call.get("resolved", False)),
            cost_usd=result.cost_usd,
            model=result.model,
            tool_calls=normalised_tools,
        )

    # ── Prompt builders (override these in subclasses) ────────────────

    def build_system_prompt(self, ctx: ChatContext) -> str:
        """Default system prompt — covers most agents.

        Subclasses can override to inject domain knowledge (the
        Validator handler, for instance, lists the rules registry; the
        Composer lists which fields are template-driven and can't be
        patched).
        """
        allow = (
            ", ".join(self.patch_allowlist) if self.patch_allowlist
            else "(none — chat only, no data mutations)"
        )
        return _SYSTEM_PROMPT_TEMPLATE.format(
            role=self.role_description,
            agent_id=self.agent_id,
            order_id=ctx.order_id,
            item_no=ctx.item_no,
            pause_context=_pretty(ctx.pause_context),
            item_data=_pretty(_redacted_item_data(ctx.item_data)),
            patch_allowlist=allow,
            static_context=_render_static_context(ctx),
            tool_catalog=_render_tool_catalog(),
        )

    # ── Internals ─────────────────────────────────────────────────────

    def _build_llm_messages(
        self, ctx: ChatContext,
    ) -> List[Dict[str, str]]:
        """Convert ChatContext + history into the OpenAI message list."""
        messages: List[Dict[str, str]] = [
            {"role": "system", "content": self.build_system_prompt(ctx)},
        ]
        for msg in ctx.messages:
            role = _MAP_ROLE.get(msg.role, "user")
            messages.append({"role": role, "content": msg.content})
        return messages


# ── Generic handler (no subclass needed) ────────────────────────────────────


class GenericChatHandler(AgentChatHandler):
    """Configurable handler for agents that don't need a custom subclass.

    Use when the only per-agent variation is the role description and
    patch allowlist — i.e. most of the catalogue.
    """

    def __init__(
        self,
        *,
        agent_id: str,
        role_description: str,
        patch_allowlist: Sequence[str] = (),
        model: str = DEFAULT_CHAT_MODEL,
        provider: Optional[LLMProvider] = None,
    ) -> None:
        super().__init__(provider=provider)
        self.agent_id = agent_id
        self.role_description = role_description
        self.patch_allowlist = tuple(patch_allowlist)
        self.model = model


# ── Registry ────────────────────────────────────────────────────────────────


_REGISTRY: Dict[str, AgentChatHandler] = {}


def register_chat_handler(handler: AgentChatHandler) -> None:
    """Register (or replace) the handler for this ``agent_id``."""
    if not handler.agent_id or handler.agent_id == "unknown":
        raise ValueError("Chat handler must set agent_id")
    _REGISTRY[handler.agent_id] = handler


def get_chat_handler(agent_id: str) -> Optional[AgentChatHandler]:
    """Return the handler for ``agent_id``, or ``None`` if unregistered.

    The dispatcher treats ``None`` as "no chat capability" and posts a
    boilerplate apology so the operator at least gets *some* signal back.
    """
    return _REGISTRY.get(agent_id)


def all_registered_agent_ids() -> List[str]:
    """For the ``/api/v1/agents`` UI to mark which agents are chattable."""
    return sorted(_REGISTRY.keys())


def clear_registry() -> None:
    """Test helper — wipe all registered handlers."""
    _REGISTRY.clear()


# ── Helpers ─────────────────────────────────────────────────────────────────


_MAP_ROLE: Dict[str, str] = {
    "agent": "assistant",
    "human": "user",
    "system": "system",
    "drawing": "user",
}


def _pretty(d: Mapping[str, Any]) -> str:
    """JSON-pretty a dict, falling back to repr if it isn't serializable."""
    try:
        return json.dumps(d, indent=2, default=str, ensure_ascii=False)
    except (TypeError, ValueError):
        return repr(d)


# Some item.data fields are megabytes (rendered SVGs, base64 PDFs).
# Redact them before stuffing into the prompt — they blow up the token
# bill and contribute nothing to the agent's reasoning.
_REDACTED_KEYS = {
    "die_cut_svg", "approval_pdf", "rendered_svg", "line_drawing_svg",
    "composed_artifacts",
}


def _redacted_item_data(data: Mapping[str, Any]) -> Dict[str, Any]:
    out: Dict[str, Any] = {}
    for k, v in (data or {}).items():
        if k in _REDACTED_KEYS:
            out[k] = f"<redacted {len(str(v))} chars>"
        else:
            out[k] = v
    return out


_SYSTEM_PROMPT_TEMPLATE = """\
You are {role} (agent_id: {agent_id}) in the LabelForge export-labeling pipeline.

You previously paused while processing order {order_id}, item {item_no}, and
opened a HITL thread so a human operator could help. The operator is now
chatting with you. Your job is to:

1. Read the pause context, current item data, and tenant summary below.
2. Engage the operator — ask clarifying questions, explain what you need.
3. Before asking the operator to paste data, check whether you already have
   it in the prefetched summary OR can fetch it via a tool call.
4. When you have enough information to proceed, propose data patches and
   signal that the block is resolved.

PAUSE CONTEXT:
{pause_context}

CURRENT ITEM DATA:
{item_data}

TENANT SUMMARY (prefetched — already in context, no tool call needed):
{static_context}

TOOL CALLS:
You may end your reply with a single fenced JSON block. The block may
contain any subset of {{"patches", "resolved", "tools"}}:

```json
{{
  "patches": {{"<field>": <value>}},
  "resolved": true|false,
  "tools": [
    {{"name": "<tool_name>", "args": {{...}}}}
  ]
}}
```

Available tools (all tenant-scoped — the tenant/order/item are bound from
context; you do NOT pass tenant_id):
{tool_catalog}

When you emit a ``tools`` array, you will be re-invoked with the results
appended to the conversation as ``[tool_result:<name>] <json>`` system
messages. Do NOT emit prose and a ``tools`` array in the same turn —
request the data first, then answer on the next turn.

You are only allowed to patch these fields: {patch_allowlist}

Set "resolved": true ONLY when you believe the block can be re-attempted
(i.e. running my agent again on the updated item.data would succeed).
Resolving auto-closes the thread and re-runs the pipeline stage; do not
guess.

STYLE:
- Keep replies conversational and short (2-4 sentences typical).
- If the operator's reply is ambiguous, ASK rather than guess.
- Never fabricate field values. If the operator hasn't given you the data
  and no tool can retrieve it, say so plainly.
- Cite concrete identifiers (rule_code, document filename, item_no) when
  you reference them so the operator can follow up.
"""


# ── Static-context + tool-catalog rendering ────────────────────────────────


def _render_static_context(ctx: "ChatContext") -> str:
    """Markdown bullets describing the prefetched tenant/order data.

    Deliberately concise — the full objects are too expensive to stuff
    into every system prompt; tools exist for that. Each bullet tells
    the LLM what's available and what tool to call for deeper data.
    """
    parts: List[str] = []

    profile = ctx.importer_profile
    if profile:
        layouts = (profile.get("panel_layouts") or {}) if isinstance(profile, Mapping) else {}
        handling = (profile.get("handling_symbol_rules") or {}) if isinstance(profile, Mapping) else {}
        brand = (profile.get("brand_treatment") or {}) if isinstance(profile, Mapping) else {}
        panel_keys = sorted(list(layouts.keys())) if isinstance(layouts, Mapping) else []
        handling_keys = sorted([k for k, v in handling.items() if v]) if isinstance(handling, Mapping) else []
        brand_name = (brand.get("company_name") or brand.get("description") or profile.get("name") or "-") if isinstance(brand, Mapping) else "-"
        parts.append(
            "- Importer profile: "
            f"brand={brand_name!r}, "
            f"panel_layouts={panel_keys[:8] or '-'}, "
            f"handling_symbols={handling_keys or '-'} "
            "(full via `get_importer_profile`)"
        )
    else:
        parts.append("- Importer profile: not yet finalized (call `get_importer_profile` or `get_onboarding_extraction`).")

    if ctx.rules_summary:
        codes = [str(r.get("rule_code") or r.get("code") or "?") for r in ctx.rules_summary[:10]]
        more = max(0, len(ctx.rules_summary) - len(codes))
        tail = f" (+{more} more)" if more else ""
        parts.append(
            f"- Active compliance rules ({len(ctx.rules_summary)}): "
            f"{codes}{tail}. Full logic via `list_compliance_rules`."
        )
    else:
        parts.append("- Active compliance rules: 0. Use `get_onboarding_extraction` to see if extraction produced rules that haven't been promoted.")

    if ctx.warnings_summary:
        labels = [str(w.get("code") or "?") for w in ctx.warnings_summary[:10]]
        more = max(0, len(ctx.warnings_summary) - len(labels))
        tail = f" (+{more} more)" if more else ""
        parts.append(
            f"- Warning labels ({len(ctx.warnings_summary)}): {labels}{tail}. "
            "Full text via `list_warning_labels`."
        )
    else:
        parts.append("- Warning labels: 0.")

    if ctx.documents_summary:
        rows = [
            f"{(d.get('id') or '?')}:{(d.get('doc_type') or '?')}:{(d.get('filename') or '?')}"
            for d in ctx.documents_summary[:20]
        ]
        parts.append(
            f"- Uploaded documents ({len(ctx.documents_summary)}): {rows}. "
            "Body text via `get_document_text(document_id=…)` or `search_documents(query=…)`."
        )
    else:
        parts.append("- Uploaded documents: none.")

    if ctx.onboarding_summary:
        agents = ctx.onboarding_summary.get("agents") if isinstance(ctx.onboarding_summary, Mapping) else None
        status = ctx.onboarding_summary.get("status") if isinstance(ctx.onboarding_summary, Mapping) else None
        extracted_keys = ctx.onboarding_summary.get("extracted_keys") if isinstance(ctx.onboarding_summary, Mapping) else None
        parts.append(
            f"- Onboarding session: status={status!r}, agents={agents!r}, "
            f"extracted_keys={extracted_keys!r}. Full payload via "
            "`get_onboarding_extraction(agent=…)`."
        )

    if ctx.sibling_items:
        sibs = [
            f"{s.get('item_no', '?')}:{s.get('state', '?')}"
            for s in ctx.sibling_items[:15]
        ]
        parts.append(
            f"- Sibling items on this order ({len(ctx.sibling_items)}): {sibs}. "
            "Full data via `get_item_data(item_no=…)`."
        )

    return "\n".join(parts) if parts else "(nothing prefetched)"


# Stable catalog text — the tools module is the source of truth, but we
# inline the descriptions here so a provider with a tiny context window
# doesn't need a separate tool-discovery roundtrip.
_TOOL_CATALOG_TEXT = """\
- `get_importer_profile()` → full brand/panels/handling payload.
- `list_compliance_rules(region?: str)` → all active rules with logic.
- `list_warning_labels(region?: str)` → approved warning labels.
- `list_importer_documents()` → uploaded docs (metadata only).
- `get_document_text(document_id: str, max_chars?: int)` → extracted text from one doc.
- `search_documents(query: str, limit?: int)` → doc filename + snippet matches.
- `get_onboarding_extraction(agent?: "protocol"|"warnings"|"checklist")` → full extracted_values from the latest session.
- `get_item_data(item_no: str)` → fused data for a sibling item on this order."""


def _render_tool_catalog() -> str:
    return _TOOL_CATALOG_TEXT


__all__ = [
    "AgentChatHandler",
    "GenericChatHandler",
    "ChatContext",
    "ChatMessage",
    "ChatReply",
    "DEFAULT_CHAT_MODEL",
    "all_registered_agent_ids",
    "clear_registry",
    "filter_patches",
    "get_chat_handler",
    "get_chat_provider",
    "parse_tool_call",
    "register_chat_handler",
    "set_chat_provider",
]
