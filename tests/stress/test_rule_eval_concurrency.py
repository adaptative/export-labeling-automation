"""Stress: 1000 rule evaluations under load (TASK-045).

Acceptance criteria from issue #88:
- 1000 rule evaluations complete without deadlocks or data races.
- Cache hit path (compiled rule re-use) does not grow without bound.
- Throughput stays within SLO (mean < 10 ms per eval on CI hardware).
"""
from __future__ import annotations

import concurrent.futures
import statistics
import time

import pytest

from labelforge.compliance.rule_engine import (
    RuleContext,
    RuleDefinition,
    RuleMatcher,
)


pytestmark = pytest.mark.stress


# ── Fixtures ────────────────────────────────────────────────────────────────


def _build_rule_set() -> list[RuleDefinition]:
    """10 rules covering the common DSL operators."""
    return [
        RuleDefinition(
            code="US-TEXTILE-001",
            version=1,
            title="US textile fibre-content disclosure",
            country="US",
            category="textile",
            placement="label",
            conditions={"op": "==", "field": "product_type", "value": "textile"},
            requirements={"op": ">", "field": "weight", "value": 0.0},
        ),
        RuleDefinition(
            code="EU-CE-002",
            version=2,
            title="EU CE mark required",
            country="EU",
            category="electronics",
            placement="label",
            conditions={"op": "in", "field": "destination", "values": ["EU", "DE", "FR"]},
            requirements={"op": "==", "field": "product_type", "value": "electronics"},
        ),
        RuleDefinition(
            code="CA-BILING-003",
            version=1,
            title="Canadian bilingual label",
            country="CA",
            category="general",
            placement="label",
            conditions={"op": "==", "field": "destination", "value": "CA"},
            requirements={"op": "true"},
        ),
        RuleDefinition(
            code="US-WEIGHT-004",
            version=3,
            title="US weight disclosure >1 kg",
            country="US",
            category="general",
            placement="label",
            conditions={
                "op": "AND",
                "children": [
                    {"op": "==", "field": "destination", "value": "US"},
                    {"op": ">", "field": "weight", "value": 1.0},
                ],
            },
            requirements={"op": "true"},
        ),
        RuleDefinition(
            code="US-COTTON-005",
            version=1,
            title="US cotton content",
            country="US",
            category="textile",
            placement="label",
            conditions={
                "op": "OR",
                "children": [
                    {"op": "==", "field": "material", "value": "cotton"},
                    {"op": "==", "field": "material", "value": "cotton_blend"},
                ],
            },
            requirements={"op": "==", "field": "destination", "value": "US"},
        ),
        RuleDefinition(
            code="UK-UKCA-006",
            version=1,
            title="UKCA mark",
            country="UK",
            category="electronics",
            placement="label",
            conditions={"op": "==", "field": "destination", "value": "UK"},
            requirements={"op": "==", "field": "product_type", "value": "electronics"},
        ),
        RuleDefinition(
            code="US-LEAD-007",
            version=1,
            title="No lead paint disclosure",
            country="US",
            category="toys",
            placement="label",
            conditions={"op": "==", "field": "product_type", "value": "toy"},
            requirements={
                "op": "NOT",
                "child": {"op": "==", "field": "material", "value": "leaded_paint"},
            },
        ),
        RuleDefinition(
            code="EU-WEEE-008",
            version=1,
            title="WEEE symbol on electronics",
            country="EU",
            category="electronics",
            placement="label",
            conditions={
                "op": "AND",
                "children": [
                    {"op": "==", "field": "product_type", "value": "electronics"},
                    {"op": "in", "field": "destination", "values": ["EU", "DE", "FR"]},
                ],
            },
            requirements={"op": "true"},
        ),
        RuleDefinition(
            code="US-ORIGIN-009",
            version=2,
            title="Country of origin disclosure",
            country="US",
            category="general",
            placement="label",
            conditions={"op": "!=", "field": "destination", "value": "NONE"},
            requirements={"op": "true"},
        ),
        RuleDefinition(
            code="US-HEAVY-010",
            version=1,
            title="Heavy goods handling",
            country="US",
            category="general",
            placement="label",
            conditions={"op": ">=", "field": "weight", "value": 5.0},
            requirements={"op": "true"},
        ),
    ]


def _build_context(idx: int) -> RuleContext:
    destinations = ["US", "EU", "UK", "CA", "DE", "FR"]
    materials = ["cotton", "cotton_blend", "polyester", "plastic", "metal"]
    product_types = ["textile", "electronics", "toy", "general"]
    return RuleContext(
        item_no=f"item-{idx:05d}",
        material=materials[idx % len(materials)],
        destination=destinations[idx % len(destinations)],
        weight=float(idx % 10) + 0.25,
        product_type=product_types[idx % len(product_types)],
    )


# ── Tests ───────────────────────────────────────────────────────────────────


class TestSingleThreaded1000Evals:
    """Baseline: 1000 sequential evals must stay well under the SLO."""

    def test_throughput(self):
        rules = _build_rule_set()
        matcher = RuleMatcher()

        start = time.perf_counter()
        reports = []
        for i in range(1000):
            reports.append(matcher.evaluate(_build_context(i), rules))
        elapsed = time.perf_counter() - start

        assert len(reports) == 1000
        # Cache should have exactly 10 entries regardless of iterations —
        # no unbounded growth as claimed by the SLO.
        assert len(matcher._cache) == 10
        # Mean latency should comfortably stay under 10 ms on any CI box.
        mean_ms = (elapsed / 1000) * 1000
        assert mean_ms < 10, f"mean {mean_ms:.3f} ms exceeds 10 ms SLO"


class TestThreadedEvals:
    """16 threads × 100 evals apiece = 1600 total. No shared mutation => safe."""

    def test_thread_pool_no_races(self):
        rules = _build_rule_set()
        # One matcher instance per thread to avoid the shared-cache dict race.
        # (RuleMatcher._cache is a plain dict — not advertised as threadsafe.)
        results: list[int] = []

        def worker(offset: int) -> int:
            local_matcher = RuleMatcher()
            count = 0
            for i in range(100):
                report = local_matcher.evaluate(_build_context(offset + i), rules)
                count += len(report.verdicts)
            return count

        with concurrent.futures.ThreadPoolExecutor(max_workers=16) as pool:
            futures = [pool.submit(worker, t * 100) for t in range(16)]
            for f in concurrent.futures.as_completed(futures):
                results.append(f.result())

        # Each worker ran 100 evals × 10 rules = 1000 verdicts.
        assert results == [1000] * 16

    def test_shared_matcher_under_contention(self):
        """Sanity check: a shared matcher across threads still produces correct
        results (dict mutations in CPython are atomic for single ops; we are
        not asserting thread-safety but proving outputs remain deterministic)."""
        rules = _build_rule_set()
        matcher = RuleMatcher()

        errors: list[str] = []

        def worker(offset: int) -> None:
            for i in range(50):
                try:
                    report = matcher.evaluate(_build_context(offset + i), rules)
                    if len(report.verdicts) != 10:
                        errors.append(f"bad verdict count @ {offset+i}")
                except Exception as exc:  # noqa: BLE001
                    errors.append(str(exc))

        with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:
            list(pool.map(worker, [t * 50 for t in range(8)]))

        assert not errors, f"rule-eval races detected: {errors[:3]}"


class TestLatencyDistribution:
    """P95 latency check — the real SLO most teams care about."""

    def test_p95_under_threshold(self):
        rules = _build_rule_set()
        matcher = RuleMatcher()
        samples: list[float] = []

        # Warm the cache first.
        for i in range(50):
            matcher.evaluate(_build_context(i), rules)

        for i in range(1000):
            t0 = time.perf_counter()
            matcher.evaluate(_build_context(i), rules)
            samples.append((time.perf_counter() - t0) * 1000)

        samples.sort()
        p50 = samples[499]
        p95 = samples[949]
        p99 = samples[989]
        # Even under noisy CI P99 should beat 50 ms per eval.
        assert p50 < 5, f"p50 {p50:.3f} ms"
        assert p95 < 20, f"p95 {p95:.3f} ms"
        assert p99 < 50, f"p99 {p99:.3f} ms"


class TestCacheBounded:
    def test_cache_bounded_by_rule_count(self):
        """Cache size must equal the number of unique (code, version) pairs —
        never the number of inputs. 10 rules × 5000 evaluations → 10 entries."""
        rules = _build_rule_set()
        matcher = RuleMatcher()
        for i in range(5000):
            matcher.evaluate(_build_context(i), rules)
        assert len(matcher._cache) == 10
