"""Line Drawing Generator core (TASK-027).

Pure-Python helpers for the HiTL manual-drawing canvas:

* :class:`Stroke`           — validated dataclass (points + color + width).
* :func:`validate_stroke`   — accepts the wire format used by the WebSocket
                              and REST endpoints and returns a :class:`Stroke`.
* :func:`strokes_to_svg`    — render a list of strokes as a self-contained SVG.
* :class:`DrawingSession`   — in-memory accumulator used by the WebSocket
                              broadcaster so late joiners can resync.
* :class:`DrawingConnectionManager` — tracks the set of active WebSockets per
                              HiTL thread so strokes sent by one user are
                              rebroadcast to every other client in the room.

The module has **no** FastAPI / SQLAlchemy dependency so it can be reused in
tests, scripts, and eventually a Celery worker.
"""
from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from typing import Any, Iterable, Optional

# Default canvas dimensions in px.  Clients may override per-session.
DEFAULT_CANVAS_WIDTH = 800
DEFAULT_CANVAS_HEIGHT = 600

# Absolute cap on points per stroke and strokes per drawing to keep
# SVG output bounded regardless of client behaviour.
_MAX_POINTS_PER_STROKE = 2000
_MAX_STROKES_PER_DRAWING = 1000


@dataclass
class Stroke:
    points: list[tuple[float, float]]
    color: str = "#000000"
    width: float = 2.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "points": [[x, y] for x, y in self.points],
            "color": self.color,
            "width": self.width,
        }


class DrawingValidationError(ValueError):
    """Raised when incoming stroke data is malformed."""


def validate_stroke(raw: Any) -> Stroke:
    """Coerce an arbitrary payload into a :class:`Stroke`.

    Accepts ``{"points": [[x, y], ...], "color"?: str, "width"?: number}``.
    Points can also be given as ``{"x": ..., "y": ...}`` dicts.  Raises
    :class:`DrawingValidationError` on any shape violation.
    """
    if not isinstance(raw, dict):
        raise DrawingValidationError("stroke must be a JSON object")

    raw_points = raw.get("points")
    if not isinstance(raw_points, list) or not raw_points:
        raise DrawingValidationError("stroke.points must be a non-empty array")
    if len(raw_points) > _MAX_POINTS_PER_STROKE:
        raise DrawingValidationError(
            f"stroke has {len(raw_points)} points; max {_MAX_POINTS_PER_STROKE}"
        )

    points: list[tuple[float, float]] = []
    for i, p in enumerate(raw_points):
        try:
            if isinstance(p, dict):
                x = float(p["x"])
                y = float(p["y"])
            elif isinstance(p, (list, tuple)) and len(p) >= 2:
                x = float(p[0])
                y = float(p[1])
            else:
                raise DrawingValidationError(f"point {i} has unknown shape")
        except (KeyError, TypeError, ValueError) as exc:
            raise DrawingValidationError(f"point {i} invalid: {exc}") from exc
        points.append((x, y))

    color = raw.get("color") or "#000000"
    if not isinstance(color, str) or len(color) > 32:
        raise DrawingValidationError("stroke.color must be a short string")

    try:
        width = float(raw.get("width", 2.0))
    except (TypeError, ValueError) as exc:
        raise DrawingValidationError(f"stroke.width invalid: {exc}") from exc
    if width <= 0 or width > 100:
        raise DrawingValidationError("stroke.width must be in (0, 100]")

    return Stroke(points=points, color=color, width=width)


def strokes_to_svg(
    strokes: Iterable[Stroke],
    *,
    width: int = DEFAULT_CANVAS_WIDTH,
    height: int = DEFAULT_CANVAS_HEIGHT,
) -> str:
    """Render a list of strokes as a self-contained SVG string."""
    paths: list[str] = []
    for stroke in strokes:
        if not stroke.points:
            continue
        head = stroke.points[0]
        tail = stroke.points[1:]
        d = f"M {head[0]:.2f},{head[1]:.2f}" + "".join(
            f" L {x:.2f},{y:.2f}" for x, y in tail
        )
        paths.append(
            f'<path d="{d}" fill="none" stroke="{stroke.color}" '
            f'stroke-width="{stroke.width:.2f}" stroke-linecap="round" '
            f'stroke-linejoin="round"/>'
        )
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" '
        f'viewBox="0 0 {width} {height}" width="{width}" height="{height}">'
        f"{''.join(paths)}</svg>"
    )


# ── In-memory session + connection tracking ─────────────────────────────────


@dataclass
class DrawingSession:
    """Accumulates the strokes a drawing has collected so far.

    Used by :class:`DrawingConnectionManager` so a client that connects
    mid-session can request a resync and see what everyone else has already
    drawn.
    """

    thread_id: str
    canvas_width: int = DEFAULT_CANVAS_WIDTH
    canvas_height: int = DEFAULT_CANVAS_HEIGHT
    strokes: list[Stroke] = field(default_factory=list)

    def add_stroke(self, stroke: Stroke) -> None:
        if len(self.strokes) >= _MAX_STROKES_PER_DRAWING:
            raise DrawingValidationError(
                f"drawing already at max {_MAX_STROKES_PER_DRAWING} strokes"
            )
        self.strokes.append(stroke)

    def clear(self) -> None:
        self.strokes.clear()

    def render_svg(self) -> str:
        return strokes_to_svg(
            self.strokes, width=self.canvas_width, height=self.canvas_height
        )

    def snapshot(self) -> dict[str, Any]:
        return {
            "thread_id": self.thread_id,
            "canvas_width": self.canvas_width,
            "canvas_height": self.canvas_height,
            "stroke_count": len(self.strokes),
            "strokes": [s.to_dict() for s in self.strokes],
        }


class DrawingConnectionManager:
    """Tracks active WebSocket clients grouped by HiTL thread.

    One instance is held at module scope by the API layer.  The manager is
    responsible for broadcasting stroke events to every connected peer and
    for maintaining a per-thread :class:`DrawingSession` replay buffer.
    """

    def __init__(self) -> None:
        self._rooms: dict[str, set[Any]] = {}
        self._sessions: dict[str, DrawingSession] = {}
        self._lock = asyncio.Lock()

    def session_for(self, thread_id: str) -> DrawingSession:
        if thread_id not in self._sessions:
            self._sessions[thread_id] = DrawingSession(thread_id=thread_id)
        return self._sessions[thread_id]

    async def connect(self, thread_id: str, websocket: Any) -> DrawingSession:
        async with self._lock:
            self._rooms.setdefault(thread_id, set()).add(websocket)
        return self.session_for(thread_id)

    async def disconnect(self, thread_id: str, websocket: Any) -> None:
        async with self._lock:
            peers = self._rooms.get(thread_id)
            if peers and websocket in peers:
                peers.discard(websocket)
                if not peers:
                    self._rooms.pop(thread_id, None)

    def peer_count(self, thread_id: str) -> int:
        return len(self._rooms.get(thread_id, ()))

    async def broadcast(
        self,
        thread_id: str,
        payload: dict[str, Any],
        *,
        exclude: Optional[Any] = None,
    ) -> int:
        """Send ``payload`` as JSON to every peer in ``thread_id``.

        Returns the number of successful sends.  Dead sockets are quietly
        removed from the room so a single broken client doesn't block the
        broadcast loop.
        """
        peers = list(self._rooms.get(thread_id, ()))
        sent = 0
        for peer in peers:
            if peer is exclude:
                continue
            try:
                await peer.send_json(payload)
                sent += 1
            except Exception:
                await self.disconnect(thread_id, peer)
        return sent

    def reset(self) -> None:
        """Test hook — clears every room and session."""
        self._rooms.clear()
        self._sessions.clear()


# Module-level singleton used by the API layer.  Tests may call
# ``drawing_manager.reset()`` to clean state between runs.
drawing_manager = DrawingConnectionManager()
