"""Order endpoints."""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Optional

import logging

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, UploadFile, File
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from labelforge.api.v1.auth import get_current_user
from labelforge.contracts import (
    OrderItem,
    OrderState,
    ItemState,
    compute_order_state,
    OrderItem as ContractOrderItem,
)
from labelforge.core.auth import TokenPayload
from labelforge.db.models import Order, OrderItemModel
from labelforge.db.session import get_db

router = APIRouter(prefix="/orders", tags=["orders"])


# ── Response models ──────────────────────────────────────────────────────────


class OrderSummary(BaseModel):
    id: str
    importer_id: str
    po_number: str
    state: OrderState
    item_count: int
    created_at: datetime
    updated_at: datetime


class OrderDetail(OrderSummary):
    items: list[OrderItem]


class OrderListResponse(BaseModel):
    orders: list[OrderSummary]
    total: int


# ── Request models ──────────────────────────────────────────────────────────


class CreateOrderRequest(BaseModel):
    importer_id: str = Field(..., min_length=1)
    po_reference: Optional[str] = None
    due_date: Optional[str] = None
    notes: Optional[str] = None


class CreateOrderResponse(BaseModel):
    id: str
    importer_id: str
    po_number: str
    state: OrderState
    item_count: int
    created_at: datetime
    message: str


class OrderActionResponse(BaseModel):
    order_id: str
    new_state: str
    message: str


class RejectRequest(BaseModel):
    reason: str = ""


# ── Helpers ──────────────────────────────────────────────────────────────────


def _compute_state(items: list) -> OrderState:
    if not items:
        return OrderState.CREATED
    contract_items = [
        ContractOrderItem(
            id=i.id,
            order_id=i.order_id,
            item_no=i.item_no,
            state=i.state,
            state_changed_at=i.state_changed_at or datetime.now(tz=timezone.utc),
            rules_snapshot_id=i.rules_snapshot_id,
            data=i.data,
        )
        for i in items
    ]
    return compute_order_state(contract_items)


# ── Endpoints ────────────────────────────────────────────────────────────────


@router.get("", response_model=OrderListResponse)
async def list_orders(
    state: Optional[OrderState] = Query(None, description="Filter by order state"),
    search: Optional[str] = Query(None, description="Search by PO number or order ID"),
    importer_id: Optional[str] = Query(None, description="Filter by importer ID"),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    _user: TokenPayload = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> OrderListResponse:
    """List orders with optional filtering."""
    # Fetch all orders for the tenant with their items eagerly loaded
    stmt = (
        select(Order)
        .where(Order.tenant_id == _user.tenant_id)
        .order_by(Order.created_at.desc())
    )

    if search:
        q = f"%{search}%"
        stmt = stmt.where(
            (Order.po_number.ilike(q)) | (Order.id.ilike(q))
        )
    if importer_id:
        stmt = stmt.where(Order.importer_id == importer_id)

    result = await db.execute(stmt)
    orders = result.scalars().all()

    # Build summaries with computed state
    summaries: list[OrderSummary] = []
    for order in orders:
        items = order.items  # loaded via selectin relationship
        computed = _compute_state(items)

        # Apply state filter in Python since state is computed
        if state is not None and computed != state:
            continue

        summaries.append(
            OrderSummary(
                id=order.id,
                importer_id=order.importer_id,
                po_number=order.po_number or "",
                state=computed,
                item_count=len(items),
                created_at=order.created_at,
                updated_at=order.updated_at,
            )
        )

    total = len(summaries)
    return OrderListResponse(orders=summaries[offset : offset + limit], total=total)


@router.get("/export", response_model=None)
async def export_orders_csv(
    state: Optional[OrderState] = Query(None),
    search: Optional[str] = Query(None),
    importer_id: Optional[str] = Query(None),
    _user: TokenPayload = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Export orders as CSV."""
    from fastapi.responses import StreamingResponse
    import io, csv
    # Reuse the same query logic as list_orders
    stmt = select(Order).where(Order.tenant_id == _user.tenant_id).order_by(Order.created_at.desc())
    if search:
        q = f"%{search}%"
        stmt = stmt.where((Order.po_number.ilike(q)) | (Order.id.ilike(q)))
    if importer_id:
        stmt = stmt.where(Order.importer_id == importer_id)
    result = await db.execute(stmt)
    orders = result.scalars().all()

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["ID", "PO Number", "Importer", "State", "Items", "Created", "Updated"])
    for o in orders:
        items = o.items
        computed = _compute_state(items)
        if state is not None and computed != state:
            continue
        writer.writerow([o.id, o.po_number or "", o.importer_id, computed.value, len(items), o.created_at.isoformat(), o.updated_at.isoformat()])

    output.seek(0)
    return StreamingResponse(
        iter([output.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename=orders-export.csv"},
    )


@router.get("/{order_id}", response_model=OrderDetail)
async def get_order(
    order_id: str,
    _user: TokenPayload = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> OrderDetail:
    """Get a single order by ID."""
    stmt = select(Order).where(
        Order.id == order_id,
        Order.tenant_id == _user.tenant_id,
    )
    result = await db.execute(stmt)
    order = result.scalar_one_or_none()

    if order is None:
        raise HTTPException(status_code=404, detail=f"Order {order_id} not found")

    items = order.items
    computed = _compute_state(items)

    order_items = [
        OrderItem(
            id=i.id,
            order_id=i.order_id,
            item_no=i.item_no,
            state=i.state,
            state_changed_at=i.state_changed_at or datetime.now(tz=timezone.utc),
            rules_snapshot_id=i.rules_snapshot_id,
            data=i.data,
        )
        for i in items
    ]

    return OrderDetail(
        id=order.id,
        importer_id=order.importer_id,
        po_number=order.po_number or "",
        state=computed,
        item_count=len(items),
        created_at=order.created_at,
        updated_at=order.updated_at,
        items=order_items,
    )


@router.get("/{order_id}/items", response_model=list[OrderItem])
async def list_order_items(
    order_id: str,
    _user: TokenPayload = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[OrderItem]:
    """List all items belonging to an order."""
    # Verify order exists
    order_check = await db.execute(
        select(Order.id).where(
            Order.id == order_id,
            Order.tenant_id == _user.tenant_id,
        )
    )
    if order_check.scalar_one_or_none() is None:
        raise HTTPException(status_code=404, detail=f"Order {order_id} not found")

    stmt = (
        select(OrderItemModel)
        .where(
            OrderItemModel.order_id == order_id,
            OrderItemModel.tenant_id == _user.tenant_id,
        )
        .order_by(OrderItemModel.item_no)
    )
    result = await db.execute(stmt)
    items = result.scalars().all()

    return [
        OrderItem(
            id=i.id,
            order_id=i.order_id,
            item_no=i.item_no,
            state=i.state,
            state_changed_at=i.state_changed_at or datetime.now(tz=timezone.utc),
            rules_snapshot_id=i.rules_snapshot_id,
            data=i.data,
        )
        for i in items
    ]


# ── Create order ────────────────────────────────────────────────────────────


@router.post("", response_model=CreateOrderResponse, status_code=201)
async def create_order(
    body: CreateOrderRequest,
    _user: TokenPayload = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> CreateOrderResponse:
    """Create a new order. Documents can be uploaded separately."""
    order_id = f"ORD-{datetime.now(timezone.utc).strftime('%Y')}-{uuid.uuid4().hex[:4].upper()}"
    po_number = body.po_reference or order_id
    now = datetime.now(timezone.utc)

    new_order = Order(
        id=order_id,
        tenant_id=_user.tenant_id,
        importer_id=body.importer_id,
        po_number=po_number,
        created_at=now,
        updated_at=now,
    )
    db.add(new_order)
    await db.commit()

    return CreateOrderResponse(
        id=order_id,
        importer_id=body.importer_id,
        po_number=po_number,
        state=OrderState.CREATED,
        item_count=0,
        created_at=now,
        message=f"Order {order_id} created. Upload documents to start the pipeline.",
    )


# ── Order-scoped document upload ────────────────────────────────────────────

_order_upload_logger = logging.getLogger(__name__)


async def _run_ai_classification(
    doc_id: str,
    tenant_id: str,
    filename: str,
    storage_key: str,
    order_id: str = "",
) -> None:
    """Background task: classify document, then extract items if PO/PI."""
    from labelforge.agents.intake_classifier import IntakeClassifierAgent
    from labelforge.config import settings as app_settings
    from labelforge.db.models import DocumentClassification
    from labelforge.db.session import async_session_factory

    # Read document content from blob store with proper text extraction
    from labelforge.api.v1.documents import get_blob_store
    from labelforge.core.doc_extract import extract_text
    store = get_blob_store()
    doc_content = ""
    raw_data = b""
    try:
        raw_data = await store.download(storage_key)
        doc_content = extract_text(raw_data, filename, max_chars=6000)
    except Exception:
        _order_upload_logger.warning("Could not read content for AI classification: %s", doc_id)

    # Run classification agent
    doc_class = "UNKNOWN"
    try:
        from labelforge.core.llm import OpenAIProvider
        provider = OpenAIProvider(api_key=app_settings.openai_api_key)
        agent = IntakeClassifierAgent(provider)
        result = await agent.execute({
            "document_content": doc_content,
            "filename": filename,
        })

        doc_class = result.data.get("doc_class", "UNKNOWN")

        # Update classification in DB
        async with async_session_factory() as db:
            cls_result = await db.execute(
                select(DocumentClassification).where(
                    DocumentClassification.document_id == doc_id,
                    DocumentClassification.tenant_id == tenant_id,
                )
            )
            classification = cls_result.scalar_one_or_none()
            if classification:
                classification.doc_class = doc_class
                classification.confidence = result.confidence
                classification.classification_status = "classified"
                await db.commit()

        _order_upload_logger.info(
            "AI classification complete: doc=%s class=%s confidence=%.2f",
            doc_id, doc_class, result.confidence,
        )
    except Exception as exc:
        _order_upload_logger.error("AI classification failed for %s: %s", doc_id, exc)
        try:
            async with async_session_factory() as db:
                cls_result = await db.execute(
                    select(DocumentClassification).where(
                        DocumentClassification.document_id == doc_id,
                        DocumentClassification.tenant_id == tenant_id,
                    )
                )
                classification = cls_result.scalar_one_or_none()
                if classification:
                    classification.classification_status = "classified"
                    await db.commit()
        except Exception:
            pass

    # ── Chain: extract items from PO/PI docs ─────────────────────────────
    if order_id and doc_class in ("PURCHASE_ORDER", "PROFORMA_INVOICE") and doc_content:
        await _run_item_extraction(
            order_id=order_id,
            tenant_id=tenant_id,
            doc_class=doc_class,
            doc_content=doc_content,
            filename=filename,
        )


async def _run_item_extraction(
    order_id: str,
    tenant_id: str,
    doc_class: str,
    doc_content: str,
    filename: str,
) -> None:
    """Extract line items from PO/PI and persist as OrderItemModel records."""
    from labelforge.config import settings as app_settings
    from labelforge.db.models import OrderItemModel, ItemStateEnum
    from labelforge.db.session import async_session_factory

    items: list[dict] = []

    try:
        if doc_class == "PURCHASE_ORDER":
            from labelforge.agents.po_parser import POParserAgent
            from labelforge.core.llm import OpenAIProvider

            provider = OpenAIProvider(api_key=app_settings.openai_api_key)
            # Wrap provider to match POParserAgent's calling convention
            wrapper = _LLMProviderWrapper(provider, app_settings.llm_default_model)
            agent = POParserAgent(llm_provider=wrapper)
            result = await agent.execute({"document_content": doc_content})

            if result.success or result.data.get("items"):
                items = result.data.get("items", [])
                _order_upload_logger.info(
                    "PO parsed: %d items from %s (confidence=%.2f)",
                    len(items), filename, result.confidence,
                )

        elif doc_class == "PROFORMA_INVOICE":
            from labelforge.agents.pi_parser import PIParserAgent

            # PI parser is deterministic — extract rows from the text content
            rows = _text_to_rows(doc_content)
            if rows:
                agent = PIParserAgent()
                # Auto-detect column mapping from the header row
                mapping = _auto_detect_pi_mapping(rows)
                result = await agent.execute({
                    "rows": rows,
                    "template_mapping": mapping,
                })
                if result.data.get("items"):
                    items = result.data.get("items", [])
                    _order_upload_logger.info(
                        "PI parsed: %d items from %s (confidence=%.2f)",
                        len(items), filename, result.confidence,
                    )

    except Exception as exc:
        _order_upload_logger.error("Item extraction failed for %s/%s: %s", order_id, filename, exc)
        return

    if not items:
        _order_upload_logger.info("No items extracted from %s for order %s", filename, order_id)
        return

    # ── Filter out footer/summary rows that lack a valid item_no ────────
    # PI extractions often include totals rows and bank details at the bottom.
    _JUNK_KEYWORDS = {"total", "usd", "bank", "pi no", "swift", "ifsc", "account", "amount", "nac/", "invoice"}
    _valid_items: list[dict] = []
    for item_data in items:
        item_no = str(item_data.get("item_no", "")).strip()
        if not item_no or item_no == "UNKNOWN":
            continue
        # Skip rows that look like summary text
        _lower = item_no.lower()
        if any(kw in _lower for kw in _JUNK_KEYWORDS):
            continue
        # For PI items: skip rows where item_no looks like a pure number
        # (e.g. "4304" = total qty, "214.195..." = total CBM) and has no
        # useful data in any field — likely a summary/totals row.
        if doc_class == "PROFORMA_INVOICE":
            try:
                float(item_no)
                # Pure numeric item_no — only reject if ALL data values are empty/None
                _has_any_data = any(
                    v for k, v in item_data.items()
                    if k != "item_no" and v is not None and v != ""
                )
                if not _has_any_data:
                    continue
            except ValueError:
                pass
        _valid_items.append(item_data)
    items = _valid_items

    if not items:
        _order_upload_logger.info("No valid items after filtering from %s for order %s", filename, order_id)
        return

    _order_upload_logger.info(
        "Extracted %d items (doc_class=%s) from %s for order %s",
        len(items), doc_class, filename, order_id,
    )

    # Persist items to DB
    try:
        async with async_session_factory() as db:
            # Get existing items so we can merge PI data into PO items
            existing = await db.execute(
                select(OrderItemModel).where(
                    OrderItemModel.order_id == order_id,
                    OrderItemModel.tenant_id == tenant_id,
                )
            )
            existing_items = {row.item_no: row for row in existing.scalars().all()}

            created = 0
            merged = 0
            for item_data in items:
                item_no = str(item_data.get("item_no", "")).strip()
                if not item_no:
                    continue

                if item_no in existing_items:
                    # Merge: update existing item's data with new fields
                    # (e.g., PI adds box_L/W/H/total_cartons to PO item)
                    existing_row = existing_items[item_no]
                    current_data = dict(existing_row.data or {})
                    for k, v in item_data.items():
                        if v is not None and v != "" and (k not in current_data or not current_data[k]):
                            current_data[k] = v
                    existing_row.data = current_data
                    merged += 1
                    _order_upload_logger.debug(
                        "Merged %s data into existing item %s in order %s",
                        doc_class, item_no, order_id,
                    )
                else:
                    new_item = OrderItemModel(
                        id=f"itm-{uuid.uuid4().hex[:8]}",
                        order_id=order_id,
                        tenant_id=tenant_id,
                        item_no=item_no,
                        state=ItemStateEnum.PARSED.value,
                        data=item_data,
                    )
                    db.add(new_item)
                    existing_items[item_no] = new_item
                    created += 1

            if created > 0 or merged > 0:
                await db.commit()
                _order_upload_logger.info(
                    "Persisted items for order %s from %s: %d created, %d merged",
                    order_id, filename, created, merged,
                )

            # Chain: auto-trigger fusion if both PO and PI items now exist
            existing_all = await db.execute(
                select(OrderItemModel).where(
                    OrderItemModel.order_id == order_id,
                    OrderItemModel.tenant_id == tenant_id,
                )
            )
            all_order_items = existing_all.scalars().all()
            has_po = any(
                (i.data or {}).get("upc") or (i.data or {}).get("description")
                for i in all_order_items
            )
            has_pi = any(
                (i.data or {}).get("box_L") or (i.data or {}).get("total_cartons")
                for i in all_order_items
            )
            if has_po and has_pi:
                _order_upload_logger.info(
                    "Both PO and PI items exist for order %s — auto-triggering fusion",
                    order_id,
                )
                await _run_fusion(order_id=order_id, tenant_id=tenant_id)

    except Exception as exc:
        _order_upload_logger.error("Failed to persist items for %s: %s", order_id, exc)


class _LLMProviderWrapper:
    """Adapts OpenAIProvider (model, messages) to the simpler (prompt, model_id) interface
    expected by POParserAgent._extract_from_text and _validate_and_enrich."""

    def __init__(self, provider, default_model: str):
        self._provider = provider
        self._model = default_model

    async def complete(self, prompt: str, model_id: str = "default"):
        messages = [{"role": "user", "content": prompt}]
        return await self._provider.complete(
            model=self._model,
            messages=messages,
            temperature=0.0,
            max_tokens=4096,
        )


def _text_to_rows(content: str) -> list[dict]:
    """Convert tab/line-separated text content into list of dicts (header row as keys).

    Handles real-world xlsx extractions where the first lines may be sheet
    separators (``--- Sheet: … ---``) or metadata rows before the actual table.
    Also merges two-row headers (parent row + sub-header row) that are common
    in proforma invoices with merged cells.
    """
    lines = [l for l in content.split("\n") if l.strip()]
    # Drop sheet-separator lines produced by _extract_xlsx
    lines = [l for l in lines if not l.strip().startswith("--- Sheet:")]
    if len(lines) < 2:
        return []

    # Detect separator
    sep = "\t" if any("\t" in l for l in lines[:5]) else ","

    # ── Find the header row ─────────────────────────────────────────────
    # For simple content (no table keywords found), use first line.
    # For real-world xlsx with metadata, score lines by keyword hits to find
    # the actual table header.
    _TABLE_KEYWORDS = {
        "item", "qty", "carton", "upc", "total", "description",
        "code", "price", "cbm", "inner", "outer", "harmoniz",
    }

    best_idx = 0
    best_kw_score = 0
    for i, line in enumerate(lines):
        fields = [f.strip() for f in line.split(sep)]
        kw_hits = sum(
            1 for f in fields
            if any(kw in f.lower() for kw in _TABLE_KEYWORDS)
        )
        non_empty = sum(1 for f in fields if f)
        # Only consider lines that have at least one keyword match.
        # Among those, pick the one with the most keyword hits; break ties
        # by number of non-empty fields.
        score = kw_hits * 1000 + non_empty
        if kw_hits > 0 and score > best_kw_score:
            best_kw_score = score
            best_idx = i

    headers = [h.strip() for h in lines[best_idx].split(sep)]
    if not headers:
        return []

    # ── Merge sub-header row if present ─────────────────────────────────
    # A sub-header row fills in columns that are empty in the parent.
    data_start = best_idx + 1
    if data_start < len(lines):
        sub_fields = [f.strip() for f in lines[data_start].split(sep)]
        # Count how many empty parent slots the candidate sub-header fills
        fills = sum(
            1 for j in range(min(len(headers), len(sub_fields)))
            if not headers[j] and sub_fields[j]
        )
        if fills >= 2:  # looks like a real sub-header
            last_parent = ""
            merged: list[str] = []
            for j in range(max(len(headers), len(sub_fields))):
                parent = headers[j] if j < len(headers) else ""
                sub = sub_fields[j] if j < len(sub_fields) else ""
                if parent:
                    last_parent = parent
                if parent and sub:
                    merged.append(f"{parent} {sub}")
                elif parent:
                    merged.append(parent)
                elif sub and last_parent:
                    merged.append(f"{last_parent} {sub}")
                elif sub:
                    merged.append(sub)
                else:
                    merged.append("")
            headers = merged
            data_start += 1  # data rows start after sub-header

    # ── Build row dicts ─────────────────────────────────────────────────
    rows: list[dict] = []
    for line in lines[data_start:]:
        cells = line.split(sep)
        row: dict[str, str] = {}
        for j, header in enumerate(headers):
            if header:
                row[header] = cells[j].strip() if j < len(cells) else ""
        if any(v for v in row.values()):
            rows.append(row)
    return rows


def _auto_detect_pi_mapping(rows: list[dict]) -> dict:
    """Auto-detect PI template mapping from column headers.

    Uses two-pass matching: first exact lowercase match, then keyword-based
    scoring to handle merged multi-row headers like "(Carton Size in Inch) Lt".
    """
    if not rows:
        return {}
    sample_keys = {k.lower().strip(): k for k in rows[0].keys()}
    mapping: dict[str, str] = {}

    # ── Pass 1: exact lowercase match ───────────────────────────────────
    exact_patterns: dict[str, list[str]] = {
        "item_no": ["buyer's item code", "item_no", "item no", "item number", "sku", "style", "style no", "article"],
        "box_L": ["box_l", "carton length", "ctn length", "l(cm)", "length(cm)", "length"],
        "box_W": ["box_w", "carton width", "ctn width", "w(cm)", "width(cm)", "width"],
        "box_H": ["box_h", "carton height", "ctn height", "h(cm)", "height(cm)", "height"],
        "total_cartons": ["total_cartons", "total cartons", "ctns", "cartons"],
        "inner_pack": ["inner_pack", "inner pack", "inner", "pcs/ctn", "pcs per ctn", "pack"],
        "hs_code": ["hs_code", "hs code", "hts", "tariff", "harmonization no.", "harmonization no"],
        "cbm": ["cbm", "cubic meters", "m3"],
    }

    for target, candidates in exact_patterns.items():
        for candidate in candidates:
            if candidate in sample_keys:
                mapping[target] = sample_keys[candidate]
                break

    # ── Pass 2: keyword scoring for remaining unmapped targets ──────────
    # Handles merged header names like "(Carton Size in Inch) Lt"
    keyword_rules: dict[str, tuple[list[str], list[str]]] = {
        # target: (required_keywords, exclude_keywords)
        "item_no": (["buyer", "item"], ["nac"]),
        "box_L": (["carton", "lt"], []),
        "box_W": (["carton", "wt"], []),
        "box_H": (["carton", "ht"], []),
        "total_cartons": (["total", "carton"], []),
        "hs_code": (["harmoniz"], []),
        "cbm": (["cbm", "per"], []),
    }

    used_keys = set(mapping.values())
    for target, (required, excluded) in keyword_rules.items():
        if target in mapping:
            continue
        best_key: str | None = None
        best_hits = 0
        for kl, orig in sample_keys.items():
            if orig in used_keys:
                continue
            if excluded and any(ex in kl for ex in excluded):
                continue
            hits = sum(1 for kw in required if kw in kl)
            if hits > best_hits and hits >= len(required):
                best_hits = hits
                best_key = orig
        if best_key:
            mapping[target] = best_key
            used_keys.add(best_key)

    return mapping


async def _run_fusion(
    order_id: str,
    tenant_id: str,
) -> None:
    """Background task: fuse PO + PI items for an order.

    Collects all PARSED items, groups by doc_class stored in item.data,
    then runs FusionAgent to merge and validate.
    """
    from labelforge.agents.fusion import FusionAgent
    from labelforge.config import settings as app_settings
    from labelforge.db.models import OrderItemModel, ItemStateEnum
    from labelforge.db.session import async_session_factory

    try:
        async with async_session_factory() as db:
            result = await db.execute(
                select(OrderItemModel).where(
                    OrderItemModel.order_id == order_id,
                    OrderItemModel.tenant_id == tenant_id,
                )
            )
            all_items = result.scalars().all()

        if not all_items:
            _order_upload_logger.info("No items to fuse for order %s", order_id)
            return

        # Build PO and PI item lists for FusionAgent.
        # After the extraction pipeline merges PO+PI data into each DB item,
        # every item holds BOTH sets of fields.  Split each item's fields into
        # its PO portion and PI portion so FusionAgent can join by item_no and
        # run its deterministic cross-validation (UPC Luhn, dimension fit,
        # weight) plus LLM material inference.
        _PO_FIELDS = {
            "item_no", "upc", "gtin", "description", "product_dims",
            "case_qty", "total_qty", "weight_kg", "unit_weight_kg",
            "material", "finish", "country_of_origin",
        }
        _PI_FIELDS = {
            "item_no", "box_L", "box_W", "box_H", "total_cartons",
            "inner_pack", "hs_code", "cbm",
        }

        po_items: list[dict] = []
        pi_items: list[dict] = []

        for item in all_items:
            data = dict(item.data or {})
            data["item_no"] = item.item_no

            has_po = any(data.get(f) for f in ("upc", "description", "total_qty"))
            has_pi = any(data.get(f) for f in ("box_L", "box_W", "total_cartons"))

            if has_po:
                po_items.append({k: v for k, v in data.items() if k in _PO_FIELDS})
            if has_pi:
                pi_items.append({k: v for k, v in data.items() if k in _PI_FIELDS})
            if not has_po and not has_pi:
                # Ambiguous — include in both so the join doesn't drop it
                po_items.append(data)
                pi_items.append(data)

        if not po_items and not pi_items:
            _order_upload_logger.info("No PO/PI items to fuse for order %s", order_id)
            return

        # Build LLM provider if API key is available
        llm_provider = None
        if app_settings.openai_api_key:
            from labelforge.core.llm import OpenAIProvider
            provider = OpenAIProvider(api_key=app_settings.openai_api_key)
            llm_provider = _LLMProviderWrapper(provider, app_settings.llm_default_model)

        agent = FusionAgent(llm_provider=llm_provider)
        fusion_result = await agent.execute({
            "po_items": po_items,
            "pi_items": pi_items,
        })

        fused_items = fusion_result.data.get("fused_items", [])
        issues = fusion_result.data.get("issues", [])

        _order_upload_logger.info(
            "Fusion complete for order %s: %d fused items, %d issues, confidence=%.2f",
            order_id, len(fused_items), len(issues), fusion_result.confidence,
        )

        # Update existing items with fused data and advance state
        async with async_session_factory() as db:
            for fused in fused_items:
                fused_item_no = str(fused.get("item_no", "")).strip()
                if not fused_item_no:
                    continue

                existing = await db.execute(
                    select(OrderItemModel).where(
                        OrderItemModel.order_id == order_id,
                        OrderItemModel.tenant_id == tenant_id,
                        OrderItemModel.item_no == fused_item_no,
                    )
                )
                db_item = existing.scalar_one_or_none()
                if db_item:
                    db_item.data = fused
                    new_state = (
                        ItemStateEnum.FUSED.value
                        if fusion_result.success
                        else ItemStateEnum.HUMAN_BLOCKED.value
                    )
                    db_item.state = new_state

            await db.commit()

        _order_upload_logger.info(
            "Fusion persisted for order %s: %d items updated to state=%s",
            order_id, len(fused_items),
            "FUSED" if fusion_result.success else "HUMAN_BLOCKED",
        )

    except Exception as exc:
        _order_upload_logger.error("Fusion failed for order %s: %s", order_id, exc)


@router.post("/{order_id}/fuse", status_code=200)
async def fuse_order_items(
    order_id: str,
    background_tasks: BackgroundTasks = BackgroundTasks(),
    _user: TokenPayload = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Trigger fusion of PO + PI items for an order.

    Merges data from purchase order and proforma invoice items,
    validates cross-document consistency, and advances item state to FUSED.
    """
    # Verify order exists
    order_check = await db.execute(
        select(Order.id).where(
            Order.id == order_id,
            Order.tenant_id == _user.tenant_id,
        )
    )
    if order_check.scalar_one_or_none() is None:
        raise HTTPException(status_code=404, detail="Order not found")

    # Check order has items
    item_count = await db.execute(
        select(func.count()).select_from(OrderItemModel).where(
            OrderItemModel.order_id == order_id,
            OrderItemModel.tenant_id == _user.tenant_id,
        )
    )
    count = item_count.scalar() or 0
    if count == 0:
        raise HTTPException(status_code=400, detail="Order has no items to fuse")

    background_tasks.add_task(
        _run_fusion,
        order_id=order_id,
        tenant_id=_user.tenant_id,
    )

    return {
        "order_id": order_id,
        "message": f"Fusion started for {count} items. Poll GET /orders/{order_id} to check state.",
        "item_count": count,
    }


@router.post("/{order_id}/documents", status_code=201)
async def upload_order_document(
    order_id: str,
    file: UploadFile = File(...),
    background_tasks: BackgroundTasks = BackgroundTasks(),
    _user: TokenPayload = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Upload a document to a specific order.

    This is a convenience endpoint that delegates to the documents module.
    """
    from labelforge.api.v1.documents import (
        get_blob_store,
        _documents,
        DocumentRecord,
        _classify_by_filename,
        _guess_doc_class,
    )
    from labelforge.core.blobstore import BlobMeta
    from labelforge.db.models import Document as DocumentModel, DocumentClassification
    from uuid import uuid4

    # Verify order exists in DB
    order_check = await db.execute(
        select(Order.id).where(
            Order.id == order_id,
            Order.tenant_id == _user.tenant_id,
        )
    )
    if order_check.scalar_one_or_none() is None:
        raise HTTPException(status_code=404, detail="Order not found")

    filename = file.filename or "unnamed.pdf"
    content = await file.read()
    size_bytes = len(content)

    if size_bytes == 0:
        raise HTTPException(status_code=400, detail="Empty file")
    if size_bytes > 25 * 1024 * 1024:
        raise HTTPException(status_code=413, detail="File exceeds 25 MB limit")

    doc_id = f"doc-{uuid.uuid4().hex[:8]}"
    storage_key = f"{order_id}/{filename}"

    store = get_blob_store()
    blob_meta: BlobMeta = await store.upload(key=storage_key, data=content, content_type=file.content_type)

    quick_class, quick_confidence = _classify_by_filename(filename)

    # Persist to database
    new_doc = DocumentModel(
        id=doc_id,
        tenant_id=_user.tenant_id,
        order_id=order_id,
        filename=filename,
        s3_key=storage_key,
        size_bytes=size_bytes,
    )
    db.add(new_doc)

    guessed_class = _guess_doc_class(filename)
    classification = DocumentClassification(
        id=str(uuid4()),
        document_id=doc_id,
        tenant_id=_user.tenant_id,
        doc_class=guessed_class.value,
        confidence=quick_confidence,
        classification_status="classifying",
    )
    db.add(classification)
    await db.commit()

    # Also track in in-memory registry for BlobStore features
    doc = DocumentRecord(
        id=doc_id,
        order_id=order_id,
        filename=filename,
        doc_class=quick_class,
        confidence=quick_confidence,
        storage_key=storage_key,
        content_hash=blob_meta.sha256,
        size_bytes=size_bytes,
        classification_status="pending",
    )
    _documents.append(doc)

    # Queue AI classification as a background task
    background_tasks.add_task(
        _run_ai_classification,
        doc_id=doc_id,
        tenant_id=_user.tenant_id,
        filename=filename,
        storage_key=storage_key,
        order_id=order_id,
    )

    return {
        "id": doc_id,
        "order_id": order_id,
        "filename": filename,
        "doc_class": quick_class,
        "confidence": quick_confidence,
        "size_bytes": size_bytes,
        "classification_status": "classifying",
        "message": f"Document '{filename}' uploaded to order {order_id}. AI classification in progress.",
    }


# ── Order actions ───────────────────────────────────────────────────────────


@router.post("/{order_id}/approve", response_model=OrderActionResponse)
async def approve_order(
    order_id: str,
    _user: TokenPayload = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> OrderActionResponse:
    """Approve an order and mark all items as DELIVERED."""
    stmt = select(Order).where(Order.id == order_id, Order.tenant_id == _user.tenant_id)
    result = await db.execute(stmt)
    order = result.scalar_one_or_none()
    if not order:
        raise HTTPException(status_code=404, detail=f"Order {order_id} not found")

    # Update all items to DELIVERED
    for item in order.items:
        item.state = "DELIVERED"
        item.state_changed_at = datetime.now(tz=timezone.utc)
    order.updated_at = datetime.now(tz=timezone.utc)
    await db.commit()

    return OrderActionResponse(order_id=order_id, new_state="DELIVERED", message="Order approved and delivered.")


@router.post("/{order_id}/reject", response_model=OrderActionResponse)
async def reject_order(
    order_id: str,
    body: RejectRequest = RejectRequest(),
    _user: TokenPayload = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> OrderActionResponse:
    """Reject an order and loop items back to INTAKE_CLASSIFIED."""
    stmt = select(Order).where(Order.id == order_id, Order.tenant_id == _user.tenant_id)
    result = await db.execute(stmt)
    order = result.scalar_one_or_none()
    if not order:
        raise HTTPException(status_code=404, detail=f"Order {order_id} not found")

    for item in order.items:
        item.state = "INTAKE_CLASSIFIED"
        item.state_changed_at = datetime.now(tz=timezone.utc)
    order.updated_at = datetime.now(tz=timezone.utc)
    await db.commit()

    return OrderActionResponse(order_id=order_id, new_state="IN_PROGRESS", message=f"Order rejected. Reason: {body.reason or 'N/A'}")


@router.post("/{order_id}/send-to-printer", response_model=OrderActionResponse)
async def send_to_printer(
    order_id: str,
    _user: TokenPayload = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> OrderActionResponse:
    """Send order to printer."""
    stmt = select(Order).where(Order.id == order_id, Order.tenant_id == _user.tenant_id)
    result = await db.execute(stmt)
    order = result.scalar_one_or_none()
    if not order:
        raise HTTPException(status_code=404, detail=f"Order {order_id} not found")

    order.updated_at = datetime.now(tz=timezone.utc)
    await db.commit()

    return OrderActionResponse(order_id=order_id, new_state=_compute_state(order.items).value, message="Order sent to printer.")


# ── Pipeline advancement (in-process, no Temporal) ──────────────────────────


class AdvanceStep(BaseModel):
    stage: str
    items_advanced: int
    needs_hitl: int
    failed: int
    cost_usd: float


class AdvanceResponse(BaseModel):
    order_id: str
    ran_steps: list[AdvanceStep]
    final_states: dict[str, int]
    stalled_reason: Optional[str] = None


# Map each current item-state to (next_state, activity coroutine factory).
# The activities live in ``labelforge.workflows.order_processor``; we call the
# wrapped function directly (bypassing the Temporal client) so that dev/demo
# environments without a running worker can still advance the pipeline.
async def _ensure_hitl_thread(
    *,
    db: AsyncSession,
    tenant_id: str,
    order_id: str,
    item_no: str,
    stage: str,
    agent_id: str,
    reason: str,
    context: dict,
) -> None:
    """Create (or no-op) a HiTL thread for a pipeline block.

    Idempotent on ``(order_id, item_no, stage)`` while a matching thread
    is still ``OPEN`` — an operator clicking "Advance pipeline" three
    times in a row will not produce three duplicate tickets.
    """
    from labelforge.db.models import HiTLThreadModel, HiTLMessageModel
    import json

    # Look up an already-open thread keyed by this stage.
    existing = await db.execute(
        select(HiTLThreadModel).where(
            HiTLThreadModel.tenant_id == tenant_id,
            HiTLThreadModel.order_id == order_id,
            HiTLThreadModel.item_no == item_no,
            HiTLThreadModel.agent_id == agent_id,
            HiTLThreadModel.status == "OPEN",
        )
    )
    if existing.scalar_one_or_none() is not None:
        return

    thread = HiTLThreadModel(
        id=str(uuid.uuid4()),
        tenant_id=tenant_id,
        order_id=order_id,
        item_no=item_no,
        agent_id=agent_id,
        priority="P2",
        status="OPEN",
    )
    db.add(thread)
    await db.flush()

    db.add(HiTLMessageModel(
        id=str(uuid.uuid4()),
        thread_id=thread.id,
        tenant_id=tenant_id,
        sender_type="agent",
        content=(
            f"{agent_id} paused at the {stage} stage and needs human input.\n\n"
            f"Reason: {reason}"
        ),
        context=context,
    ))


async def _persist_composed_artifacts(
    *,
    db: AsyncSession,
    tenant_id: str,
    item: OrderItemModel,
    composed_artifacts: dict,
) -> None:
    """Materialise die-cut SVGs generated by the ComposerAgent.

    Writes an ``Artifact`` row + uploads the SVG bytes to the configured
    BlobStore so the per-item preview (``GET /items/{id}/diecut-svg``) can
    stream it. Idempotent: if an artifact with the same content-hash
    already exists for this item + type we skip the upload.
    """
    import hashlib
    from labelforge.api.v1.documents import get_blob_store
    from labelforge.db.models import Artifact

    art = composed_artifacts.get(item.item_no) or composed_artifacts.get(str(item.item_no))
    if not art:
        return
    svg = (art.get("die_cut_svg") or "").strip()
    if not svg:
        return

    data = svg.encode("utf-8")
    content_hash = f"sha256:{hashlib.sha256(data).hexdigest()}"

    # Dedup by (item, type, hash) — re-running advance should not create
    # duplicate Artifact rows for the same SVG.
    existing = (await db.execute(
        select(Artifact).where(
            Artifact.order_item_id == item.id,
            Artifact.tenant_id == tenant_id,
            Artifact.artifact_type == "die_cut_svg",
            Artifact.content_hash == content_hash,
        )
    )).scalar_one_or_none()
    if existing is not None:
        return

    store = get_blob_store()
    s3_key = f"artifacts/{item.id}/die_cut_svg/{content_hash.split(':')[-1][:16]}.svg"
    await store.upload(s3_key, data, content_type="image/svg+xml")

    db.add(Artifact(
        id=str(uuid.uuid4()),
        tenant_id=tenant_id,
        order_item_id=item.id,
        artifact_type="die_cut_svg",
        s3_key=s3_key,
        content_hash=content_hash,
        size_bytes=len(data),
        mime_type="image/svg+xml",
        provenance={
            "source": "advance_order_pipeline",
            "placements": art.get("placements") or [],
        },
    ))


async def _persist_line_drawing(
    *,
    db: AsyncSession,
    tenant_id: str,
    item: OrderItemModel,
    line_drawings_svg: dict,
) -> None:
    """Materialise the per-item line drawing generated by
    ``generate_drawing_activity``.

    Writes an ``Artifact`` row + uploads the SVG bytes to the BlobStore
    so ``GET /items/{id}/line-drawing`` can stream it. Without this the
    Line Drawing tab on the item preview page returns 404 even when the
    payload already carries the vectorised SVG under
    ``item.data["line_drawings_svg"][item_no]``.

    Mirrors :func:`_persist_composed_artifacts` — idempotent via
    (item, type, hash) dedup.
    """
    import hashlib
    from labelforge.api.v1.documents import get_blob_store
    from labelforge.db.models import Artifact

    svg = (line_drawings_svg.get(item.item_no)
           or line_drawings_svg.get(str(item.item_no))
           or "").strip()
    if not svg:
        return

    data = svg.encode("utf-8")
    content_hash = f"sha256:{hashlib.sha256(data).hexdigest()}"

    existing = (await db.execute(
        select(Artifact).where(
            Artifact.order_item_id == item.id,
            Artifact.tenant_id == tenant_id,
            Artifact.artifact_type == "line_drawing",
            Artifact.content_hash == content_hash,
        )
    )).scalar_one_or_none()
    if existing is not None:
        return

    store = get_blob_store()
    s3_key = f"artifacts/{item.id}/line_drawing/{content_hash.split(':')[-1][:16]}.svg"
    await store.upload(s3_key, data, content_type="image/svg+xml")

    db.add(Artifact(
        id=str(uuid.uuid4()),
        tenant_id=tenant_id,
        order_item_id=item.id,
        artifact_type="line_drawing",
        s3_key=s3_key,
        content_hash=content_hash,
        size_bytes=len(data),
        mime_type="image/svg+xml",
        provenance={"source": "generate_drawing_activity"},
    ))


async def _load_importer_profile_payload(
    db: AsyncSession, importer_id: str, tenant_id: str,
) -> dict:
    """Assemble the ``importer_profile`` dict the Compose + Validate
    activities expect: the base Importer record merged with the latest
    ``ImporterProfileModel`` row (brand_treatment, panel_layouts,
    handling_symbol_rules, etc.).

    Returns ``{}`` if the importer has no profile yet — Compose will
    fall back to demo defaults and the Validator will flag missing
    profile fields as Critical.
    """
    from labelforge.db.models import Importer, ImporterProfileModel as IPM

    imp = (await db.execute(
        select(Importer).where(
            Importer.id == importer_id,
            Importer.tenant_id == tenant_id,
        )
    )).scalar_one_or_none()
    if imp is None:
        return {}

    prof = (await db.execute(
        select(IPM)
        .where(IPM.importer_id == importer_id, IPM.tenant_id == tenant_id)
        .order_by(IPM.version.desc())
        .limit(1)
    )).scalar_one_or_none()

    return {
        "importer_id": imp.id,
        "name": imp.name,
        "code": imp.code,
        "version": (prof.version if prof else 0),
        "brand_treatment": (prof.brand_treatment if prof else None) or {},
        "panel_layouts": (prof.panel_layouts if prof else None) or {},
        "handling_symbol_rules": (prof.handling_symbol_rules if prof else None) or {},
        "pi_template_mapping": (prof.pi_template_mapping if prof else None) or {},
        "logo_asset_hash": (prof.logo_asset_hash if prof else None),
    }


async def _persist_approval_pdf_for_order(
    *,
    db: AsyncSession,
    tenant_id: str,
    order: Order,
) -> None:
    """Generate one approval PDF per order and attach it to every
    composed item as an ``Artifact`` row.

    Idempotent on ``content_hash`` — if the composition inputs haven't
    changed, no new blob is uploaded and no new rows are inserted.
    """
    from labelforge.api.v1.documents import get_blob_store
    from labelforge.db.models import Artifact
    from labelforge.services.approval_pdf import generate_approval_pdf

    # Gather items that have a composed artifact on record — regardless
    # of whether they're currently sitting in HUMAN_BLOCKED (compose
    # succeeded earlier but a later stage blocked them). We intentionally
    # key off ``composed_artifacts`` presence instead of ``item.state``
    # so rerunning the pipeline doesn't strand the approval PDF.
    items_payload: list[dict] = []
    composed_by_item_no: dict[str, dict] = {}
    for it in order.items:
        ca = (it.data or {}).get("composed_artifacts") or {}
        art = ca.get(it.item_no) or ca.get(str(it.item_no))
        if not art:
            continue
        d = dict(it.data or {})
        d.pop("fused_items", None)
        d.pop("rules", None)
        items_payload.append({"item_no": it.item_no, **d})
        composed_by_item_no[it.item_no] = art
    if not items_payload:
        return

    order_dict = {
        "id": order.id,
        "po_number": order.po_number,
        "importer_id": order.importer_id,
        "tenant_id": tenant_id,
    }
    pdf_bytes, provenance = generate_approval_pdf(
        order=order_dict,
        items=items_payload,
        composed_artifacts=composed_by_item_no,
    )
    content_hash = provenance.get("content_hash") or ""
    if not content_hash:
        import hashlib
        content_hash = f"sha256:{hashlib.sha256(pdf_bytes).hexdigest()}"

    # Skip upload if any existing item artifact already has this hash.
    existing_any = (await db.execute(
        select(Artifact).where(
            Artifact.tenant_id == tenant_id,
            Artifact.artifact_type == "approval_pdf",
            Artifact.content_hash == content_hash,
        ).limit(1)
    )).scalar_one_or_none()

    s3_key = f"artifacts/{order.id}/approval_pdf/{content_hash.split(':')[-1][:16]}.pdf"
    if existing_any is None:
        store = get_blob_store()
        await store.upload(s3_key, pdf_bytes, content_type="application/pdf")
    else:
        s3_key = existing_any.s3_key

    # One Artifact row per composed item so the per-item preview endpoint
    # can stream the same PDF without an extra join.
    for it in order.items:
        if it.item_no not in composed_by_item_no:
            continue
        dup = (await db.execute(
            select(Artifact).where(
                Artifact.order_item_id == it.id,
                Artifact.tenant_id == tenant_id,
                Artifact.artifact_type == "approval_pdf",
                Artifact.content_hash == content_hash,
            )
        )).scalar_one_or_none()
        if dup is not None:
            continue
        db.add(Artifact(
            id=str(uuid.uuid4()),
            tenant_id=tenant_id,
            order_item_id=it.id,
            artifact_type="approval_pdf",
            s3_key=s3_key,
            content_hash=content_hash,
            size_bytes=len(pdf_bytes),
            mime_type="application/pdf",
            provenance={
                "source": "advance_order_pipeline",
                "order_id": order.id,
                **{k: v for k, v in provenance.items() if k != "frozen_inputs"},
            },
        ))


async def _rescue_resolved_items(
    db: AsyncSession,
    *,
    tenant_id: str,
    order: Order,
) -> int:
    """Move HUMAN_BLOCKED items whose HiTL threads are all resolved
    back to their ``last_successful_state``.

    Rationale: a block fires when an activity returns ``needs_hitl``;
    the advance endpoint flips the item to HUMAN_BLOCKED and opens a
    thread. Once the operator resolves (or we escalate) every thread
    linked to that item, the item is no longer blocked on anything —
    but the state flag stays HUMAN_BLOCKED forever because the
    ``_STAGE_PLAN`` loop only fires on active pipeline states.

    This helper is the inverse of the block-writing path: it finds
    every HUMAN_BLOCKED item on ``order``, checks the OPEN thread
    count for ``(order_id, item_no)``, and if zero remain it resets
    the item to ``last_successful_state`` (falling back to ``FUSED``
    when the marker is missing for any reason). The block breadcrumbs
    are stripped so the UI pipeline tracker stops painting the item
    orange. Returns the number of items rescued.
    """
    from labelforge.db.models import HiTLThreadModel

    blocked = [it for it in order.items if it.state == "HUMAN_BLOCKED"]
    if not blocked:
        return 0

    rescued = 0
    for item in blocked:
        open_count = (await db.execute(
            select(func.count(HiTLThreadModel.id)).where(
                HiTLThreadModel.tenant_id == tenant_id,
                HiTLThreadModel.order_id == order.id,
                HiTLThreadModel.item_no == item.item_no,
                HiTLThreadModel.status == "OPEN",
            )
        )).scalar_one()
        if open_count:
            continue

        data = dict(item.data or {})
        resume_state = str(data.get("last_successful_state") or "FUSED")
        data.pop("blocked_at_stage", None)
        data.pop("blocked_reason", None)
        item.data = data
        item.state = resume_state
        item.state_changed_at = datetime.now(tz=timezone.utc)
        rescued += 1

    if rescued:
        await db.flush()
    return rescued


_STAGE_PLAN: list[tuple[str, str, str]] = [
    ("FUSED",             "COMPLIANCE_EVAL",  "compliance_eval_activity"),
    ("COMPLIANCE_EVAL",   "DRAWING_GENERATED", "generate_drawing_activity"),
    ("DRAWING_GENERATED", "COMPOSED",         "compose_label_activity"),
    ("COMPOSED",          "VALIDATED",        "validate_output_activity"),
    # VALIDATED → REVIEWED / DELIVERED is driven by the human approval
    # endpoints (``/approve``) and is deliberately out of scope here.
]


@router.post("/{order_id}/advance", response_model=AdvanceResponse)
async def advance_order_pipeline(
    order_id: str,
    force: bool = Query(
        False,
        description=(
            "When false (default, used by the auto-advance hook that fires "
            "after a HiTL Resolve), only the self-heal rescue pass runs — "
            "items whose threads are all RESOLVED flip back to their "
            "``last_successful_state`` and the endpoint returns. The "
            "``_STAGE_PLAN`` cascade is skipped so the just-unblocked item "
            "does not immediately re-validate, re-fail, and spawn a new "
            "HiTL thread. When true (frontend 'Advance pipeline' button), "
            "the full cascade runs after rescue — the operator is explicitly "
            "asking to retry validation."
        ),
    ),
    _user: TokenPayload = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> AdvanceResponse:
    """Synchronously advance every item on the order one stage at a time.

    Intended as a local-dev / demo fallback when the Temporal worker is not
    running. Each stage's activity function is imported on demand from the
    workflow module and called directly with an ``ActivityInput``; results
    are written back to ``OrderItemModel`` under the same transaction.
    """
    from labelforge.workflows.order_processor import (
        ActivityInput,
        compliance_eval_activity,
        generate_drawing_activity,
        compose_label_activity,
        validate_output_activity,
    )

    activity_fns = {
        "compliance_eval_activity":  compliance_eval_activity,
        "generate_drawing_activity": generate_drawing_activity,
        "compose_label_activity":    compose_label_activity,
        "validate_output_activity":  validate_output_activity,
    }

    stmt = select(Order).where(Order.id == order_id, Order.tenant_id == _user.tenant_id)
    result = await db.execute(stmt)
    order = result.scalar_one_or_none()
    if order is None:
        raise HTTPException(status_code=404, detail=f"Order {order_id} not found")

    ran_steps: list[AdvanceStep] = []
    stalled_reason: Optional[str] = None

    # Self-heal: rescue items that are sitting in HUMAN_BLOCKED when all
    # of their linked HiTL threads have been resolved. The per-item
    # ``blocked_at_stage`` + ``last_successful_state`` breadcrumbs the
    # pipeline leaves behind tell us exactly where to resume from. This
    # is the fix for the "order stays Human Blocked even after I
    # resolved all threads" complaint — the resolver's auto-advance
    # hook calls this endpoint, and now that call actually moves the
    # needle instead of no-op-ing because every item sits outside the
    # ``_STAGE_PLAN`` from-state set.
    unblocked = await _rescue_resolved_items(
        db,
        tenant_id=_user.tenant_id,
        order=order,
    )

    # Load the importer profile once — Compose & Validate both need it.
    importer_profile_payload = await _load_importer_profile_payload(
        db, order.importer_id, _user.tenant_id,
    )

    if unblocked:
        ran_steps.append(AdvanceStep(
            stage="UNBLOCKED",
            items_advanced=unblocked,
            needs_hitl=0,
            failed=0,
            cost_usd=0.0,
        ))
        await db.commit()
        # Soft-advance: stop here unless the caller explicitly asked to
        # re-run validation. Without this guard the auto-advance hook that
        # fires on every HiTL Resolve would immediately push the just-
        # unblocked item back through ``_STAGE_PLAN`` — and since resolving
        # a thread does not mutate ``item.data``, validation would fail
        # for the same reason and spawn a fresh HiTL thread. Net effect
        # for the operator: resolve one, see one appear; inbox count
        # never drops. The frontend 'Advance pipeline' button passes
        # ``force=true`` for the hard-retry path.
        if not force:
            tally: dict[str, int] = {}
            for it in order.items:
                tally[it.state] = tally.get(it.state, 0) + 1
            return AdvanceResponse(
                order_id=order_id,
                ran_steps=ran_steps,
                final_states=tally,
                stalled_reason=None,
            )

    for from_state, to_state, activity_name in _STAGE_PLAN:
        candidates = [it for it in order.items if it.state == from_state]
        if not candidates:
            continue

        fn = activity_fns[activity_name]
        step_advanced = 0
        step_hitl = 0
        step_failed = 0
        step_cost = 0.0

        # Collect fused_items once per run so compliance/compose/validate all
        # see the same denormalised payload shape expected by their activity
        # bodies (see compliance_eval_activity docstring). Inject the
        # order's ``po_number`` onto each item so the SHORT-panel info
        # block ("P.O NO.:") renders correctly — the item.data carries
        # the item identifier but not the parent order's PO.
        fused_items_payload = [
            {
                **(it.data or {}),
                "item_no": it.item_no,
                "item_id": it.id,
                "po_number": order.po_number,
            }
            for it in order.items
            if it.state in {
                "FUSED", "COMPLIANCE_EVAL", "DRAWING_GENERATED", "COMPOSED", "VALIDATED",
            }
        ]

        for item in candidates:
            payload = dict(item.data or {})
            # Enrich per-item payload the same way fused_items_payload is
            # enriched so the single-item view Composer + Validator see
            # consistent data.
            payload["item_no"] = item.item_no
            payload["po_number"] = order.po_number
            payload["fused_items"] = fused_items_payload
            payload["importer_profile"] = importer_profile_payload
            try:
                out = await fn(ActivityInput(
                    order_id=order_id,
                    item_id=item.id,
                    tenant_id=_user.tenant_id,
                    document_id=None,
                    payload=payload,
                ))
            except Exception as exc:  # pragma: no cover — defensive
                step_failed += 1
                stalled_reason = f"{activity_name} raised {type(exc).__name__}: {exc}"
                item.state = "FAILED"
                item.state_changed_at = datetime.now(tz=timezone.utc)
                continue

            # IMPORTANT: strip transient activity-payload keys *before*
            # merging into ``item.data``. Activities like compliance_eval
            # return their ``input.payload`` verbatim, which includes the
            # cross-item ``fused_items`` blob we injected. If we persisted
            # that back into each item's row, the next advance call would
            # include the already-embedded ``fused_items`` from step N-1
            # inside step N's ``fused_items``, multiplying the JSON size
            # exponentially (1.2 GB after four iterations on an 8-item order).
            _TRANSIENT_KEYS = {"fused_items", "rules", "default_destination"}
            incoming = {k: v for k, v in (out.data or {}).items() if k not in _TRANSIENT_KEYS}
            new_data = {**(item.data or {}), **incoming}
            # Also scrub any legacy recursion already present on the row.
            for k in _TRANSIENT_KEYS:
                new_data.pop(k, None)
            if out.success:
                item.state = out.new_state or to_state
                step_advanced += 1
                # Clear any previous block marker on successful progression.
                new_data.pop("blocked_at_stage", None)
                new_data.pop("blocked_reason", None)
                new_data["last_successful_state"] = item.state
                # When the Composer stage completes, persist the generated
                # die-cut SVG as a real ``Artifact`` + BlobStore object so
                # ``GET /items/{id}/diecut-svg`` can stream it. Without
                # this hook, ``composed_artifacts`` only lived inline on
                # ``item.data`` and the preview page showed
                # "die-cut SVG unavailable".
                if to_state == "COMPOSED":
                    await _persist_composed_artifacts(
                        db=db,
                        tenant_id=_user.tenant_id,
                        item=item,
                        composed_artifacts=(out.data or {}).get("composed_artifacts") or {},
                    )
                # Same for Drawings: without this hook the vectorised
                # line-art generated by ProductImageProcessorAgent only
                # lives inline on item.data, and the Line Drawing tab
                # on the item preview page 404s because the Artifact
                # row doesn't exist.
                if to_state == "DRAWING_GENERATED":
                    await _persist_line_drawing(
                        db=db,
                        tenant_id=_user.tenant_id,
                        item=item,
                        line_drawings_svg=(out.data or {}).get("line_drawings_svg") or {},
                    )
            else:
                # Preserve the stage this item WAS trying to reach so the UI
                # can colour the pipeline tracker correctly — without this,
                # every stage pill goes orange when any single stage blocks.
                new_data["blocked_at_stage"] = to_state
                if out.hitl_reason:
                    new_data["blocked_reason"] = out.hitl_reason
                if out.needs_hitl:
                    step_hitl += 1
                    item.state = "HUMAN_BLOCKED"
                    # Raise a HiTL thread so the operator sees this block in
                    # the Inbox and can provide the missing input. Idempotent
                    # on ``(order_id, item_no, stage, OPEN)`` so repeated
                    # advance calls don't spam the queue.
                    await _ensure_hitl_thread(
                        db=db,
                        tenant_id=_user.tenant_id,
                        order_id=order_id,
                        item_no=item.item_no,
                        stage=to_state,
                        agent_id=activity_name,
                        reason=out.hitl_reason or f"Agent for stage {to_state} needs human input",
                        context={
                            "item_id": item.id,
                            "stage": to_state,
                            "activity": activity_name,
                            "reason": out.hitl_reason,
                        },
                    )
                else:
                    step_failed += 1
                    item.state = out.new_state or "FAILED"
            item.data = new_data
            item.state_changed_at = datetime.now(tz=timezone.utc)
            step_cost += float(out.cost_usd or 0.0)

        # Once the Compose stage has run (even partially), materialise a
        # single order-scoped approval PDF and attach it as an Artifact row
        # for every composed item. The preview endpoint is per-item but
        # the document itself is an order-level deliverable.
        if to_state == "COMPOSED" and step_advanced > 0:
            await _persist_approval_pdf_for_order(
                db=db,
                tenant_id=_user.tenant_id,
                order=order,
            )

        ran_steps.append(AdvanceStep(
            stage=to_state,
            items_advanced=step_advanced,
            needs_hitl=step_hitl,
            failed=step_failed,
            cost_usd=round(step_cost, 6),
        ))

        # If any item in this step blocked or failed, we stop advancing — the
        # operator needs to resolve the HiTL thread or inspect the failure.
        if step_hitl or step_failed:
            stalled_reason = stalled_reason or (
                f"{step_hitl} item(s) need HITL" if step_hitl else "pipeline failure"
            )
            break

    order.updated_at = datetime.now(tz=timezone.utc)
    await db.commit()

    # Final per-state counts for the caller.
    tally: dict[str, int] = {}
    for it in order.items:
        tally[it.state] = tally.get(it.state, 0) + 1

    return AdvanceResponse(
        order_id=order_id,
        ran_steps=ran_steps,
        final_states=tally,
        stalled_reason=stalled_reason,
    )
