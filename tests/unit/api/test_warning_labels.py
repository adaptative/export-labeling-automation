"""Tests for warning-labels library CRUD + approval workflow (INT-011)."""
from __future__ import annotations

import pytest

from labelforge.api.v1.auth import _make_stub_jwt


PREFIX = "/api/v1/warning-labels"


@pytest.fixture
def compliance_headers():
    token = _make_stub_jwt(
        "usr-compliance-001",
        "tnt-nakoda-001",
        "COMPLIANCE",
        "compliance@nakodacraft.com",
    )
    return {"Authorization": f"Bearer {token}"}


def _create(client, headers, code="PEANUT_WARNING", **overrides) -> dict:
    payload = {
        "code": code,
        "title": "Peanut allergen warning",
        "text": "Contains peanuts. May cause severe allergic reaction.",
        "region": "US",
        "placement": "product",
        "size_mm_width": 50,
        "size_mm_height": 75,
        "trigger_conditions": {"contains": "peanuts"},
        "variants": [
            {"language": "en", "text": "Contains peanuts.", "size": "50x75"},
            {"language": "es", "text": "Contiene cacahuetes.", "size": "50x75"},
        ],
    }
    payload.update(overrides)
    resp = client.post(PREFIX, json=payload, headers=headers)
    assert resp.status_code == 201, resp.text
    return resp.json()


# ── Create ──────────────────────────────────────────────────────────────────


class TestWarningLabelCreate:
    def test_create_admin(self, client, admin_headers):
        data = _create(client, admin_headers, code="NEW_ADMIN")
        assert data["code"] == "NEW_ADMIN"
        assert data["status"] == "pending"
        assert data["active"] is False
        assert data["size_mm_width"] == 50
        assert data["trigger_conditions"] == {"contains": "peanuts"}
        assert isinstance(data["variants"], list) and len(data["variants"]) == 2
        assert data["created_by"] == "usr-admin-001"

    def test_create_compliance(self, client, compliance_headers):
        data = _create(client, compliance_headers, code="NEW_COMP")
        assert data["status"] == "pending"

    def test_create_ops_forbidden(self, client, ops_headers):
        resp = client.post(
            PREFIX,
            json={"code": "OPS_DENY", "title": "x", "text": "y"},
            headers=ops_headers,
        )
        assert resp.status_code == 403

    def test_create_unauthenticated(self, client):
        resp = client.post(PREFIX, json={"code": "X", "title": "x", "text": "y"})
        assert resp.status_code == 401

    def test_create_duplicate_code_409(self, client, admin_headers):
        _create(client, admin_headers, code="DUP")
        resp = client.post(
            PREFIX,
            json={"code": "DUP", "title": "dup", "text": "dup text"},
            headers=admin_headers,
        )
        assert resp.status_code == 409

    def test_create_missing_fields_422(self, client, admin_headers):
        resp = client.post(
            PREFIX, json={"code": "BAD"}, headers=admin_headers
        )
        assert resp.status_code == 422


# ── List / search / filter ──────────────────────────────────────────────────


class TestWarningLabelList:
    def test_list_includes_created(self, client, admin_headers):
        d = _create(client, admin_headers, code="LISTED")
        resp = client.get(PREFIX, headers=admin_headers)
        assert resp.status_code == 200
        codes = [w["code"] for w in resp.json()["warning_labels"]]
        assert "LISTED" in codes

    def test_filter_by_status(self, client, admin_headers):
        d = _create(client, admin_headers, code="STATUS_FILTER")
        resp = client.get(
            f"{PREFIX}?status=pending", headers=admin_headers
        )
        assert resp.status_code == 200
        assert any(w["id"] == d["id"] for w in resp.json()["warning_labels"])

        resp = client.get(
            f"{PREFIX}?status=approved", headers=admin_headers
        )
        assert all(w["id"] != d["id"] for w in resp.json()["warning_labels"])

    def test_filter_invalid_status_400(self, client, admin_headers):
        resp = client.get(f"{PREFIX}?status=NOPE", headers=admin_headers)
        assert resp.status_code == 400

    def test_search_matches_title(self, client, admin_headers):
        _create(client, admin_headers, code="SEARCH_ME", title="UNIQUETITLETOKEN")
        resp = client.get(
            f"{PREFIX}?search=UNIQUETITLETOKEN", headers=admin_headers
        )
        assert resp.status_code == 200
        codes = [w["code"] for w in resp.json()["warning_labels"]]
        assert "SEARCH_ME" in codes

    def test_search_matches_text(self, client, admin_headers):
        _create(
            client,
            admin_headers,
            code="SEARCH_TXT",
            text="Warning: contains trace amounts of MAGICPHRASE999.",
        )
        resp = client.get(
            f"{PREFIX}?search=MAGICPHRASE999", headers=admin_headers
        )
        assert resp.status_code == 200
        assert any(
            w["code"] == "SEARCH_TXT" for w in resp.json()["warning_labels"]
        )

    def test_filter_by_active(self, client, admin_headers):
        d = _create(client, admin_headers, code="ACTIVE_FILTER")
        resp = client.get(f"{PREFIX}?active=true", headers=admin_headers)
        ids = [w["id"] for w in resp.json()["warning_labels"]]
        assert d["id"] not in ids  # pending labels are inactive


# ── Get ──────────────────────────────────────────────────────────────────────


class TestWarningLabelGet:
    def test_get_existing(self, client, admin_headers):
        d = _create(client, admin_headers, code="GET_ME")
        resp = client.get(f"{PREFIX}/{d['id']}", headers=admin_headers)
        assert resp.status_code == 200
        assert resp.json()["id"] == d["id"]

    def test_get_not_found(self, client, admin_headers):
        resp = client.get(f"{PREFIX}/does-not-exist", headers=admin_headers)
        assert resp.status_code == 404


# ── Update ──────────────────────────────────────────────────────────────────


class TestWarningLabelUpdate:
    def test_update_text(self, client, admin_headers):
        d = _create(client, admin_headers, code="UPD")
        resp = client.put(
            f"{PREFIX}/{d['id']}",
            json={"text": "New exact legal wording v2."},
            headers=admin_headers,
        )
        assert resp.status_code == 200
        assert resp.json()["text"] == "New exact legal wording v2."

    def test_update_variants(self, client, admin_headers):
        d = _create(client, admin_headers, code="UPD_VAR")
        variants = [
            {"language": "en", "text": "English", "size": "60x80"},
            {"language": "fr", "text": "Français", "size": "60x80"},
        ]
        resp = client.put(
            f"{PREFIX}/{d['id']}",
            json={"variants": variants},
            headers=admin_headers,
        )
        assert resp.status_code == 200
        assert resp.json()["variants"] == variants

    def test_update_ops_forbidden(self, client, admin_headers, ops_headers):
        d = _create(client, admin_headers, code="UPD_OPS")
        resp = client.put(
            f"{PREFIX}/{d['id']}",
            json={"title": "nope"},
            headers=ops_headers,
        )
        assert resp.status_code == 403

    def test_update_approved_label_keeps_code_immutable(
        self, client, admin_headers
    ):
        """Code is never sent in update body, so it can never change."""
        d = _create(client, admin_headers, code="IMMUT")
        client.post(f"{PREFIX}/{d['id']}/approve", headers=admin_headers)
        resp = client.put(
            f"{PREFIX}/{d['id']}",
            json={"title": "Revised title"},
            headers=admin_headers,
        )
        assert resp.status_code == 200
        assert resp.json()["code"] == "IMMUT"  # unchanged


# ── Approve / Reject / Deprecate ────────────────────────────────────────────


class TestWarningLabelApprove:
    def test_approve_flips_status_and_active(self, client, admin_headers):
        d = _create(client, admin_headers, code="APPROVE")
        resp = client.post(
            f"{PREFIX}/{d['id']}/approve", headers=admin_headers
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["status"] == "approved"
        assert body["active"] is True
        assert body["approved_by"] == "usr-admin-001"
        assert body["approved_at"] is not None

    def test_approve_compliance_role(self, client, compliance_headers):
        d = _create(client, compliance_headers, code="COMP_APPROVE")
        resp = client.post(
            f"{PREFIX}/{d['id']}/approve", headers=compliance_headers
        )
        assert resp.status_code == 200

    def test_approve_ops_forbidden(self, client, admin_headers, ops_headers):
        d = _create(client, admin_headers, code="OPS_CANT_APPROVE")
        resp = client.post(
            f"{PREFIX}/{d['id']}/approve", headers=ops_headers
        )
        assert resp.status_code == 403

    def test_approve_twice_409(self, client, admin_headers):
        d = _create(client, admin_headers, code="TWICE")
        client.post(f"{PREFIX}/{d['id']}/approve", headers=admin_headers)
        resp = client.post(
            f"{PREFIX}/{d['id']}/approve", headers=admin_headers
        )
        assert resp.status_code == 409

    def test_approve_not_found(self, client, admin_headers):
        resp = client.post(f"{PREFIX}/nope/approve", headers=admin_headers)
        assert resp.status_code == 404

    def test_approve_clears_rejected_reason(self, client, admin_headers):
        d = _create(client, admin_headers, code="REJECT_THEN_APPROVE")
        client.post(
            f"{PREFIX}/{d['id']}/reject",
            json={"reason": "wrong wording"},
            headers=admin_headers,
        )
        resp = client.post(
            f"{PREFIX}/{d['id']}/approve", headers=admin_headers
        )
        assert resp.status_code == 200
        assert resp.json()["rejected_reason"] is None


class TestWarningLabelReject:
    def test_reject_requires_reason(self, client, admin_headers):
        d = _create(client, admin_headers, code="REJ_NOREASON")
        resp = client.post(
            f"{PREFIX}/{d['id']}/reject", json={}, headers=admin_headers
        )
        assert resp.status_code == 422

    def test_reject_sets_status_and_reason(self, client, admin_headers):
        d = _create(client, admin_headers, code="REJ_OK")
        resp = client.post(
            f"{PREFIX}/{d['id']}/reject",
            json={"reason": "regulatory text does not match FDA §101.9"},
            headers=admin_headers,
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["status"] == "rejected"
        assert body["active"] is False
        assert "FDA" in body["rejected_reason"]

    def test_reject_approved_label_409(self, client, admin_headers):
        d = _create(client, admin_headers, code="REJ_APPROVED")
        client.post(f"{PREFIX}/{d['id']}/approve", headers=admin_headers)
        resp = client.post(
            f"{PREFIX}/{d['id']}/reject",
            json={"reason": "too late"},
            headers=admin_headers,
        )
        assert resp.status_code == 409

    def test_reject_ops_forbidden(self, client, admin_headers, ops_headers):
        d = _create(client, admin_headers, code="REJ_OPS")
        resp = client.post(
            f"{PREFIX}/{d['id']}/reject",
            json={"reason": "x"},
            headers=ops_headers,
        )
        assert resp.status_code == 403


class TestWarningLabelDeprecate:
    def test_deprecate_approved(self, client, admin_headers):
        d = _create(client, admin_headers, code="DEP")
        client.post(f"{PREFIX}/{d['id']}/approve", headers=admin_headers)
        resp = client.post(
            f"{PREFIX}/{d['id']}/deprecate", headers=admin_headers
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["status"] == "deprecated"
        assert body["active"] is False

    def test_deprecate_pending_409(self, client, admin_headers):
        d = _create(client, admin_headers, code="DEP_PENDING")
        resp = client.post(
            f"{PREFIX}/{d['id']}/deprecate", headers=admin_headers
        )
        assert resp.status_code == 409

    def test_deprecated_cannot_be_re_approved(self, client, admin_headers):
        d = _create(client, admin_headers, code="DEP_NO_REAPPROVE")
        client.post(f"{PREFIX}/{d['id']}/approve", headers=admin_headers)
        client.post(f"{PREFIX}/{d['id']}/deprecate", headers=admin_headers)
        resp = client.post(
            f"{PREFIX}/{d['id']}/approve", headers=admin_headers
        )
        assert resp.status_code == 409


# ── Tenant isolation ────────────────────────────────────────────────────────


class TestTenantIsolation:
    def test_cross_tenant_get_404(self, client, admin_headers):
        d = _create(client, admin_headers, code="PRIVATE_LABEL")
        other_token = _make_stub_jwt(
            "usr-other", "tnt-other", "ADMIN", "other@other.com"
        )
        headers = {"Authorization": f"Bearer {other_token}"}
        resp = client.get(f"{PREFIX}/{d['id']}", headers=headers)
        assert resp.status_code == 404

    def test_cross_tenant_list_excludes(self, client, admin_headers):
        d = _create(client, admin_headers, code="TENANT_ISOLATE")
        other_token = _make_stub_jwt(
            "usr-other", "tnt-other", "ADMIN", "other@other.com"
        )
        headers = {"Authorization": f"Bearer {other_token}"}
        resp = client.get(PREFIX, headers=headers)
        assert resp.status_code == 200
        ids = [w["id"] for w in resp.json()["warning_labels"]]
        assert d["id"] not in ids


# ── Full lifecycle ──────────────────────────────────────────────────────────


class TestFullLifecycle:
    def test_e2e_create_edit_approve(self, client, admin_headers):
        """Create → edit text → approve → verify appears in active filter."""
        created = _create(client, admin_headers, code="E2E_FLOW")
        assert created["status"] == "pending"

        # Edit the regulatory text.
        edit_resp = client.put(
            f"{PREFIX}/{created['id']}",
            json={"text": "Final FDA-compliant wording v3."},
            headers=admin_headers,
        )
        assert edit_resp.status_code == 200
        assert edit_resp.json()["text"] == "Final FDA-compliant wording v3."

        # Approve.
        approve_resp = client.post(
            f"{PREFIX}/{created['id']}/approve", headers=admin_headers
        )
        assert approve_resp.status_code == 200
        assert approve_resp.json()["active"] is True

        # Verify active filter now picks it up.
        list_resp = client.get(
            f"{PREFIX}?active=true&code=E2E_FLOW", headers=admin_headers
        )
        assert list_resp.json()["total"] == 1
