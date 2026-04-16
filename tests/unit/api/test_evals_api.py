"""Tests for /api/v1/evals (Sprint-16, INT-013)."""
from __future__ import annotations

import time

import pytest

from labelforge.agents.registry import AGENT_CATALOGUE
from labelforge.api.v1 import evals as evals_mod


@pytest.fixture(autouse=True)
def _reset_eval_store():
    evals_mod.reset_store()
    yield
    evals_mod.reset_store()


class TestListEvals:
    def test_requires_auth(self, client):
        resp = client.get("/api/v1/evals")
        assert resp.status_code in (401, 403)

    def test_first_call_seeds_baseline(self, client, admin_headers):
        resp = client.get("/api/v1/evals", headers=admin_headers)
        assert resp.status_code == 200
        body = resp.json()
        # Baseline = one per agent.
        assert body["total"] == len(AGENT_CATALOGUE)
        assert len(body["evals"]) == len(AGENT_CATALOGUE)

    def test_eval_result_shape(self, client, admin_headers):
        body = client.get("/api/v1/evals", headers=admin_headers).json()
        for ev in body["evals"]:
            assert "id" in ev
            assert "agent_id" in ev
            assert "agent_name" in ev
            assert "status" in ev
            assert ev["status"] in {"pass", "fail", "warn", "running"}
            metrics = ev["metrics"]
            for field in (
                "precision",
                "recall",
                "f1_score",
                "accuracy",
                "cost_delta",
                "sample_size",
            ):
                assert field in metrics
            assert 0 <= metrics["precision"] <= 1
            assert 0 <= metrics["recall"] <= 1

    def test_agent_id_filter(self, client, admin_headers):
        target = AGENT_CATALOGUE[0]["agent_id"]
        body = client.get(
            f"/api/v1/evals?agent_id={target}", headers=admin_headers
        ).json()
        assert body["total"] == 1
        assert body["evals"][0]["agent_id"] == target

    def test_results_sorted_desc_by_date(self, client, admin_headers):
        body = client.get("/api/v1/evals", headers=admin_headers).json()
        dates = [e["eval_date"] for e in body["evals"]]
        assert dates == sorted(dates, reverse=True)


class TestGetEval:
    def test_known_id(self, client, admin_headers):
        # Seed first by hitting list.
        client.get("/api/v1/evals", headers=admin_headers)
        target = AGENT_CATALOGUE[0]["agent_id"]
        eval_id = f"ev-{target}-baseline"
        resp = client.get(f"/api/v1/evals/{eval_id}", headers=admin_headers)
        assert resp.status_code == 200
        assert resp.json()["id"] == eval_id

    def test_unknown_id_404(self, client, admin_headers):
        resp = client.get("/api/v1/evals/nope", headers=admin_headers)
        assert resp.status_code == 404


class TestRunAllEvals:
    def test_run_all_returns_202_with_batch_id(self, client, admin_headers):
        resp = client.post("/api/v1/evals/run-all", headers=admin_headers)
        assert resp.status_code == 202
        body = resp.json()
        assert "eval_batch_id" in body
        assert body["status"] in {"queued", "running", "completed"}
        assert body["started_at"] > 0

    def test_polling_returns_status(self, client, admin_headers):
        resp = client.post("/api/v1/evals/run-all", headers=admin_headers)
        batch_id = resp.json()["eval_batch_id"]

        # Poll until completed or timeout (5s).
        deadline = time.time() + 5.0
        while time.time() < deadline:
            poll = client.get(
                f"/api/v1/evals/run-all/{batch_id}", headers=admin_headers
            )
            assert poll.status_code == 200
            body = poll.json()
            if body["status"] == "completed":
                break
            time.sleep(0.05)
        assert body["status"] == "completed"
        assert body["total"] == len(AGENT_CATALOGUE)
        assert body["completed"] == len(AGENT_CATALOGUE)
        assert len(body["results"]) == len(AGENT_CATALOGUE)
        assert body["finished_at"] is not None

    def test_polling_unknown_batch_404(self, client, admin_headers):
        resp = client.get(
            "/api/v1/evals/run-all/does-not-exist", headers=admin_headers
        )
        assert resp.status_code == 404


class TestRecordEvalResult:
    def test_record_and_read_back(self, client, admin_headers):
        # Use the public helper directly; endpoint should surface it.
        evals_mod.record_eval_result(
            evals_mod.EvalResult(
                id="ev-custom-1",
                agent_id="fusion_agent",
                agent_name="Fusion Agent",
                eval_date=time.time(),
                status="pass",
                metrics=evals_mod.EvalMetrics(
                    precision=0.95,
                    recall=0.93,
                    f1_score=0.94,
                    accuracy=0.95,
                    cost_delta=-1.0,
                    sample_size=120,
                ),
            )
        )
        resp = client.get("/api/v1/evals/ev-custom-1", headers=admin_headers)
        assert resp.status_code == 200
        assert resp.json()["metrics"]["precision"] == 0.95
