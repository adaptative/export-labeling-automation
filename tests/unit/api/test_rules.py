"""Tests for rule management endpoints (TASK-025 / Sprint 10)."""
from __future__ import annotations

import pytest

from labelforge.api.v1.auth import _make_stub_jwt


PREFIX = "/api/v1/rules"


@pytest.fixture
def compliance_headers():
    token = _make_stub_jwt(
        "usr-compliance-001", "tnt-nakoda-001", "COMPLIANCE", "compliance@nakodacraft.com"
    )
    return {"Authorization": f"Bearer {token}"}


def _create_rule(client, headers, code="TEST_RULE", **overrides) -> dict:
    payload = {
        "code": code,
        "title": "Test rule",
        "description": "desc",
        "region": "US",
        "placement": "both",
        "logic": {
            "conditions": {"op": "==", "field": "destination", "value": "US"},
            "requirements": {"op": "==", "field": "material", "value": "wood"},
            "category": "safety",
        },
    }
    payload.update(overrides)
    resp = client.post(PREFIX, json=payload, headers=headers)
    assert resp.status_code == 201, resp.text
    return resp.json()


# ── CRUD + lifecycle ────────────────────────────────────────────────────────


class TestRuleCreate:
    def test_create_rule_admin(self, client, admin_headers):
        data = _create_rule(client, admin_headers, code="NEW_RULE_ADMIN")
        assert data["code"] == "NEW_RULE_ADMIN"
        assert data["version"] == 1
        assert data["active"] is False  # staging

    def test_create_rule_compliance(self, client, compliance_headers):
        data = _create_rule(client, compliance_headers, code="NEW_RULE_COMP")
        assert data["active"] is False

    def test_create_rule_ops_forbidden(self, client, ops_headers):
        resp = client.post(
            PREFIX,
            json={"code": "OPS_RULE", "title": "x"},
            headers=ops_headers,
        )
        assert resp.status_code == 403

    def test_create_rule_unauthenticated(self, client):
        resp = client.post(PREFIX, json={"code": "X", "title": "x"})
        assert resp.status_code == 401

    def test_create_second_version_bumps(self, client, admin_headers):
        _create_rule(client, admin_headers, code="BUMP")
        data2 = _create_rule(client, admin_headers, code="BUMP")
        assert data2["version"] == 2

    def test_create_missing_fields_rejected(self, client, admin_headers):
        resp = client.post(PREFIX, json={"code": "BAD"}, headers=admin_headers)
        assert resp.status_code == 422


class TestRuleList:
    def test_list_includes_created(self, client, admin_headers):
        d = _create_rule(client, admin_headers, code="LISTED")
        resp = client.get(PREFIX, headers=admin_headers)
        assert resp.status_code == 200
        codes = [r["code"] for r in resp.json()["rules"]]
        assert "LISTED" in codes
        assert any(r["id"] == d["id"] for r in resp.json()["rules"])

    def test_filter_by_active(self, client, admin_headers):
        d = _create_rule(client, admin_headers, code="FILTER_ME")
        # Only active — the new rule is staged so it won't appear.
        resp = client.get(PREFIX + "?active=true", headers=admin_headers)
        ids = [r["id"] for r in resp.json()["rules"]]
        assert d["id"] not in ids

    def test_filter_by_code(self, client, admin_headers):
        _create_rule(client, admin_headers, code="UNIQUE_FILTER_CODE")
        resp = client.get(PREFIX + "?code=UNIQUE_FILTER_CODE", headers=admin_headers)
        assert resp.status_code == 200
        assert resp.json()["total"] == 1

    def test_list_ordering_version_desc(self, client, admin_headers):
        _create_rule(client, admin_headers, code="ORDERED")
        _create_rule(client, admin_headers, code="ORDERED")
        resp = client.get(PREFIX + "?code=ORDERED", headers=admin_headers)
        versions = [r["version"] for r in resp.json()["rules"]]
        assert versions == [2, 1]


class TestRuleGet:
    def test_get_existing(self, client, admin_headers):
        d = _create_rule(client, admin_headers, code="GET_ME")
        resp = client.get(f"{PREFIX}/{d['id']}", headers=admin_headers)
        assert resp.status_code == 200
        assert resp.json()["id"] == d["id"]

    def test_get_not_found(self, client, admin_headers):
        resp = client.get(f"{PREFIX}/rule-nope", headers=admin_headers)
        assert resp.status_code == 404


class TestRuleUpdate:
    def test_update_staged_rule(self, client, admin_headers):
        d = _create_rule(client, admin_headers, code="UPD")
        resp = client.put(
            f"{PREFIX}/{d['id']}",
            json={"title": "Updated Title"},
            headers=admin_headers,
        )
        assert resp.status_code == 200
        assert resp.json()["title"] == "Updated Title"

    def test_update_active_rule_409(self, client, admin_headers):
        d = _create_rule(client, admin_headers, code="UPD_ACTIVE")
        client.post(f"{PREFIX}/{d['id']}/promote", headers=admin_headers)
        resp = client.put(
            f"{PREFIX}/{d['id']}",
            json={"title": "too late"},
            headers=admin_headers,
        )
        assert resp.status_code == 409

    def test_update_ops_forbidden(self, client, admin_headers, ops_headers):
        d = _create_rule(client, admin_headers, code="UPD_OPS")
        resp = client.put(
            f"{PREFIX}/{d['id']}",
            json={"title": "nope"},
            headers=ops_headers,
        )
        assert resp.status_code == 403


class TestRulePromote:
    def test_promote_activates_rule(self, client, admin_headers):
        d = _create_rule(client, admin_headers, code="PROMOTE_ME")
        resp = client.post(f"{PREFIX}/{d['id']}/promote", headers=admin_headers)
        assert resp.status_code == 200
        assert resp.json()["active"] is True

        get_resp = client.get(f"{PREFIX}/{d['id']}", headers=admin_headers)
        assert get_resp.json()["active"] is True

    def test_promote_deactivates_older_version(self, client, admin_headers):
        v1 = _create_rule(client, admin_headers, code="TWO_VERSIONS")
        client.post(f"{PREFIX}/{v1['id']}/promote", headers=admin_headers)

        v2 = _create_rule(client, admin_headers, code="TWO_VERSIONS")
        client.post(f"{PREFIX}/{v2['id']}/promote", headers=admin_headers)

        r1 = client.get(f"{PREFIX}/{v1['id']}", headers=admin_headers).json()
        r2 = client.get(f"{PREFIX}/{v2['id']}", headers=admin_headers).json()
        assert r1["active"] is False
        assert r2["active"] is True

    def test_promote_compliance_role(self, client, compliance_headers):
        d = _create_rule(client, compliance_headers, code="COMP_PROMOTE")
        resp = client.post(
            f"{PREFIX}/{d['id']}/promote", headers=compliance_headers
        )
        assert resp.status_code == 200

    def test_promote_ops_forbidden(self, client, admin_headers, ops_headers):
        d = _create_rule(client, admin_headers, code="OPS_CANT")
        resp = client.post(f"{PREFIX}/{d['id']}/promote", headers=ops_headers)
        assert resp.status_code == 403

    def test_promote_already_active_409(self, client, admin_headers):
        d = _create_rule(client, admin_headers, code="ALREADY_ON")
        client.post(f"{PREFIX}/{d['id']}/promote", headers=admin_headers)
        resp = client.post(f"{PREFIX}/{d['id']}/promote", headers=admin_headers)
        assert resp.status_code == 409

    def test_promote_not_found(self, client, admin_headers):
        resp = client.post(f"{PREFIX}/rule-nope/promote", headers=admin_headers)
        assert resp.status_code == 404


class TestRuleRollback:
    def test_rollback_deactivates_and_restores_previous(self, client, admin_headers):
        v1 = _create_rule(client, admin_headers, code="ROLLME")
        client.post(f"{PREFIX}/{v1['id']}/promote", headers=admin_headers)
        v2 = _create_rule(client, admin_headers, code="ROLLME")
        client.post(f"{PREFIX}/{v2['id']}/promote", headers=admin_headers)

        resp = client.post(f"{PREFIX}/{v2['id']}/rollback", headers=admin_headers)
        assert resp.status_code == 200

        r1 = client.get(f"{PREFIX}/{v1['id']}", headers=admin_headers).json()
        r2 = client.get(f"{PREFIX}/{v2['id']}", headers=admin_headers).json()
        assert r1["active"] is True
        assert r2["active"] is False

    def test_rollback_no_previous_just_deactivates(self, client, admin_headers):
        d = _create_rule(client, admin_headers, code="LONELY")
        client.post(f"{PREFIX}/{d['id']}/promote", headers=admin_headers)
        resp = client.post(f"{PREFIX}/{d['id']}/rollback", headers=admin_headers)
        assert resp.status_code == 200
        r = client.get(f"{PREFIX}/{d['id']}", headers=admin_headers).json()
        assert r["active"] is False

    def test_rollback_staged_rule_409(self, client, admin_headers):
        d = _create_rule(client, admin_headers, code="NEVER_LIVE")
        resp = client.post(f"{PREFIX}/{d['id']}/rollback", headers=admin_headers)
        assert resp.status_code == 409

    def test_rollback_ops_forbidden(self, client, admin_headers, ops_headers):
        d = _create_rule(client, admin_headers, code="OPS_ROLLBACK")
        client.post(f"{PREFIX}/{d['id']}/promote", headers=admin_headers)
        resp = client.post(f"{PREFIX}/{d['id']}/rollback", headers=ops_headers)
        assert resp.status_code == 403


class TestRuleDryRun:
    def test_dry_run_with_sample_contexts(self, client, admin_headers):
        body = {
            "proposed": {
                "code": "DRY_TEST",
                "title": "Dry run rule",
                "description": "x",
                "region": "US",
                "placement": "both",
                "logic": {
                    "conditions": {"op": "==", "field": "destination", "value": "US"},
                    "requirements": {"op": "==", "field": "material", "value": "wood"},
                },
            },
            "sample_contexts": [
                {"item_no": "ITM-1", "destination": "US", "material": "wood"},
                {"item_no": "ITM-2", "destination": "US", "material": "plastic"},
                {"item_no": "ITM-3", "destination": "EU", "material": "wood"},
            ],
        }
        resp = client.post(f"{PREFIX}/dry-run", json=body, headers=admin_headers)
        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert data["items_evaluated"] == 3
        # ITM-2 is US + plastic → newly failing. ITM-3 is EU → not applicable. ITM-1 passes.
        assert "ITM-2" in data["newly_failing"]
        assert "ITM-1" not in data["newly_failing"]

    def test_dry_run_ops_forbidden(self, client, ops_headers):
        body = {
            "proposed": {"code": "X", "title": "t"},
            "sample_contexts": [{"item_no": "A"}],
        }
        resp = client.post(f"{PREFIX}/dry-run", json=body, headers=ops_headers)
        assert resp.status_code == 403


class TestRuleAuditLog:
    def test_audit_log_records_create_and_promote(self, client, admin_headers):
        d = _create_rule(client, admin_headers, code="AUDIT_ME")
        client.post(f"{PREFIX}/{d['id']}/promote", headers=admin_headers)

        resp = client.get(
            f"{PREFIX}/audit-log?rule_id={d['id']}", headers=admin_headers
        )
        assert resp.status_code == 200
        data = resp.json()
        actions = [e["action"] for e in data["entries"]]
        assert "create" in actions
        assert "promote" in actions

    def test_audit_log_ops_forbidden(self, client, ops_headers):
        resp = client.get(f"{PREFIX}/audit-log", headers=ops_headers)
        assert resp.status_code == 403

    def test_audit_log_filters_by_rule(self, client, admin_headers):
        a = _create_rule(client, admin_headers, code="AUDIT_A")
        b = _create_rule(client, admin_headers, code="AUDIT_B")
        resp = client.get(
            f"{PREFIX}/audit-log?rule_id={a['id']}", headers=admin_headers
        )
        ids = {e["rule_id"] for e in resp.json()["entries"]}
        assert ids == {a["id"]}
        assert b["id"] not in ids


class TestTenantIsolation:
    def test_cross_tenant_get_404(self, client, admin_headers):
        d = _create_rule(client, admin_headers, code="PRIVATE")
        other_token = _make_stub_jwt(
            "usr-other", "tnt-other", "ADMIN", "other@other.com"
        )
        other_headers = {"Authorization": f"Bearer {other_token}"}
        resp = client.get(f"{PREFIX}/{d['id']}", headers=other_headers)
        assert resp.status_code == 404
