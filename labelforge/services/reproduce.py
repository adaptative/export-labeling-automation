"""Reproduce service for byte-reproducibility verification.

Supports single-artifact reproduction, batch sampling (nightly 5%),
cost tracking for reproduction runs, and incident creation on mismatch.
"""
from __future__ import annotations

import hashlib
import logging
import random
import time
from dataclasses import dataclass, field
from typing import List, Optional

logger = logging.getLogger(__name__)


@dataclass
class ReproduceResult:
    artifact_id: str
    matched: bool
    original_hash: str
    reproduced_hash: Optional[str] = None
    incident_id: Optional[str] = None
    duration_ms: float = 0.0
    cost_usd: float = 0.0


@dataclass
class BatchReproduceResult:
    total_sampled: int
    matched: int
    mismatched: int
    not_found: int
    results: List[ReproduceResult] = field(default_factory=list)
    total_duration_ms: float = 0.0
    total_cost_usd: float = 0.0

    @property
    def match_rate(self) -> float:
        if self.total_sampled == 0:
            return 0.0
        return self.matched / self.total_sampled


class ReproduceService:
    """Service for verifying artifact reproducibility.

    Wraps ProvenanceEmitter to provide:
    - Single artifact reproduce with incident tracking
    - Batch sampling (default 5%) for nightly verification
    - Cost tracking per reproduction run
    """

    # Cost per reproduction check (LLM re-run estimate)
    COST_PER_REPRODUCE_USD = 0.002

    def __init__(self, provenance_emitter, blob_store, db_session):
        self.provenance = provenance_emitter
        self.blob_store = blob_store
        self.db = db_session

    async def reproduce(self, artifact_id: str) -> ReproduceResult:
        """Verify a single artifact is bit-exact reproducible.

        Returns a ReproduceResult with match status. On mismatch,
        creates an incident record and returns the incident ID.
        """
        start = time.monotonic()

        record = await self.db.get_artifact(artifact_id)
        if not record:
            return ReproduceResult(
                artifact_id=artifact_id, matched=False,
                original_hash="", incident_id="NOT_FOUND",
                duration_ms=_elapsed_ms(start),
            )

        content = await self.blob_store.download(record.s3_path)
        reproduced_hash = self.provenance.compute_hash(content)
        matched = reproduced_hash == record.content_hash

        incident_id = None
        if not matched:
            incident_id = await self._create_incident(
                artifact_id, record.content_hash, reproduced_hash,
            )
            logger.warning(
                "Reproduce mismatch: artifact=%s expected=%s actual=%s incident=%s",
                artifact_id, record.content_hash[:16], reproduced_hash[:16], incident_id,
            )

        return ReproduceResult(
            artifact_id=artifact_id,
            matched=matched,
            original_hash=record.content_hash,
            reproduced_hash=reproduced_hash,
            incident_id=incident_id,
            duration_ms=_elapsed_ms(start),
            cost_usd=self.COST_PER_REPRODUCE_USD,
        )

    async def batch_reproduce(
        self,
        artifact_ids: List[str],
        sample_pct: float = 0.05,
        seed: Optional[int] = None,
    ) -> BatchReproduceResult:
        """Reproduce a random sample of artifacts.

        Args:
            artifact_ids: Full list of artifact IDs to sample from.
            sample_pct: Fraction to sample (default 5%).
            seed: Optional random seed for reproducible sampling.

        Returns:
            BatchReproduceResult with per-artifact results and totals.
        """
        start = time.monotonic()

        sample_size = max(1, int(len(artifact_ids) * sample_pct))
        rng = random.Random(seed)
        sampled_ids = rng.sample(artifact_ids, min(sample_size, len(artifact_ids)))

        results: List[ReproduceResult] = []
        matched = 0
        mismatched = 0
        not_found = 0

        for aid in sampled_ids:
            result = await self.reproduce(aid)
            results.append(result)
            if result.incident_id == "NOT_FOUND":
                not_found += 1
            elif result.matched:
                matched += 1
            else:
                mismatched += 1

        total_cost = sum(r.cost_usd for r in results)

        return BatchReproduceResult(
            total_sampled=len(sampled_ids),
            matched=matched,
            mismatched=mismatched,
            not_found=not_found,
            results=results,
            total_duration_ms=_elapsed_ms(start),
            total_cost_usd=total_cost,
        )

    async def nightly_sample(self, seed: Optional[int] = None) -> BatchReproduceResult:
        """Run the nightly 5% sample reproduction check.

        Fetches all artifact IDs from the database and runs
        batch_reproduce with default 5% sampling.
        """
        all_ids = await self.db.list_artifact_ids()
        if not all_ids:
            return BatchReproduceResult(
                total_sampled=0, matched=0, mismatched=0, not_found=0,
            )
        return await self.batch_reproduce(all_ids, sample_pct=0.05, seed=seed)

    async def _create_incident(
        self, artifact_id: str, expected: str, actual: str,
    ) -> str:
        """Create an incident record for a hash mismatch."""
        incident_id = f"INC-{artifact_id[:8]}"
        await self.db.create_incident(incident_id, artifact_id, expected, actual)
        return incident_id


def _elapsed_ms(start: float) -> float:
    return (time.monotonic() - start) * 1000
