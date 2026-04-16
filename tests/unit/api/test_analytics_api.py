"""Tests for GET /api/v1/analytics/automation-rate (Sprint-16, INT-019)."""
from __future__ import annotations

import pytest


class TestAutomationRate:
    def test_requires_auth(self, client):
        resp = client.get("/api/v1/analytics/automation-rate")
        assert resp.status_code in (401, 403)

    def test_default_period_30d(self, client, admin_headers):
        resp = client.get("/api/v1/analytics/automation-rate", headers=admin_headers)
        assert resp.status_code == 200
        body = resp.json()
        assert body["period_days"] == 30
        assert len(body["points"]) == 30

    def test_custom_period_7d(self, client, admin_headers):
        resp = client.get(
            "/api/v1/analytics/automation-rate?period=7d", headers=admin_headers
        )
        assert resp.status_code == 200
        assert resp.json()["period_days"] == 7

    def test_weeks_period(self, client, admin_headers):
        resp = client.get(
            "/api/v1/analytics/automation-rate?period=2w", headers=admin_headers
        )
        assert resp.status_code == 200
        assert resp.json()["period_days"] == 14

    def test_invalid_period_400(self, client, admin_headers):
        resp = client.get(
            "/api/v1/analytics/automation-rate?period=potato", headers=admin_headers
        )
        assert resp.status_code == 400

    def test_period_out_of_bounds_400(self, client, admin_headers):
        resp = client.get(
            "/api/v1/analytics/automation-rate?period=999d", headers=admin_headers
        )
        assert resp.status_code == 400

    def test_point_shape(self, client, admin_headers):
        resp = client.get(
            "/api/v1/analytics/automation-rate?period=7d", headers=admin_headers
        )
        for pt in resp.json()["points"]:
            for field in (
                "date",
                "rate_percent",
                "intake_errors",
                "fusion_errors",
                "compliance_errors",
                "total_items",
            ):
                assert field in pt
            assert 0 <= pt["rate_percent"] <= 100
            assert pt["intake_errors"] >= 0
            assert pt["fusion_errors"] >= 0
            assert pt["compliance_errors"] >= 0
            assert pt["total_items"] >= 0

    def test_points_chronological(self, client, admin_headers):
        resp = client.get(
            "/api/v1/analytics/automation-rate?period=10d", headers=admin_headers
        )
        dates = [p["date"] for p in resp.json()["points"]]
        assert dates == sorted(dates)

    def test_summary_shape(self, client, admin_headers):
        resp = client.get(
            "/api/v1/analytics/automation-rate?period=14d", headers=admin_headers
        )
        summary = resp.json()["summary"]
        for field in (
            "current_rate",
            "average_rate",
            "target_low",
            "target_high",
            "trend_pct",
            "top_error_stage",
        ):
            assert field in summary
        assert summary["target_low"] == 60.0
        assert summary["target_high"] == 85.0
        assert summary["top_error_stage"] in {
            "intake",
            "fusion",
            "compliance",
            "none",
        }

    def test_summary_current_matches_last_point(self, client, admin_headers):
        body = client.get(
            "/api/v1/analytics/automation-rate?period=7d", headers=admin_headers
        ).json()
        last_point = body["points"][-1]
        assert body["summary"]["current_rate"] == last_point["rate_percent"]

    def test_deterministic_synthetic_fill(self, client, admin_headers):
        """For empty tenants, synthetic points must be stable across calls.

        The seed is derived from ``abs(hash(tenant_id)) % 10_000`` plus the
        day's ordinal so a fresh DB gives the same demo chart every time.
        """
        first = client.get(
            "/api/v1/analytics/automation-rate?period=7d", headers=admin_headers
        ).json()
        second = client.get(
            "/api/v1/analytics/automation-rate?period=7d", headers=admin_headers
        ).json()
        # Each synthetic day's rate is deterministic per tenant.
        assert [p["rate_percent"] for p in first["points"]] == [
            p["rate_percent"] for p in second["points"]
        ]


# ── Pure-function unit tests ─────────────────────────────────────────────────


from labelforge.api.v1 import analytics as analytics_mod
from labelforge.api.v1.analytics import AutomationRatePoint


class TestParsePeriod:
    def test_days(self):
        assert analytics_mod._parse_period("30d") == 30

    def test_weeks(self):
        assert analytics_mod._parse_period("4w") == 28

    def test_case_insensitive(self):
        assert analytics_mod._parse_period("30D") == 30

    def test_invalid_format_raises(self):
        from fastapi import HTTPException

        with pytest.raises(HTTPException) as exc:
            analytics_mod._parse_period("abc")
        assert exc.value.status_code == 400

    def test_zero_invalid(self):
        from fastapi import HTTPException

        with pytest.raises(HTTPException):
            analytics_mod._parse_period("0d")

    def test_huge_invalid(self):
        from fastapi import HTTPException

        with pytest.raises(HTTPException):
            analytics_mod._parse_period("500d")


class TestRateFromBucket:
    def test_empty_bucket(self):
        assert analytics_mod._rate_from_bucket({}) == (0.0, 0)

    def test_all_blocked(self):
        rate, total = analytics_mod._rate_from_bucket({"HUMAN_BLOCKED": 10})
        assert rate == 0.0
        assert total == 10

    def test_mix(self):
        rate, total = analytics_mod._rate_from_bucket(
            {"DELIVERED": 6, "HUMAN_BLOCKED": 4}
        )
        assert total == 10
        assert rate == 60.0


class TestSummarise:
    def test_empty_points(self):
        s = analytics_mod._summarise([])
        assert s.current_rate == 0.0
        assert s.top_error_stage == "none"
        assert s.best_day is None
        assert s.worst_day is None

    def test_best_and_worst_found(self):
        pts = [
            AutomationRatePoint(
                date="2025-01-01",
                rate_percent=50.0,
                intake_errors=0,
                fusion_errors=0,
                compliance_errors=0,
                total_items=10,
            ),
            AutomationRatePoint(
                date="2025-01-02",
                rate_percent=90.0,
                intake_errors=0,
                fusion_errors=0,
                compliance_errors=0,
                total_items=10,
            ),
            AutomationRatePoint(
                date="2025-01-03",
                rate_percent=70.0,
                intake_errors=2,
                fusion_errors=0,
                compliance_errors=5,
                total_items=10,
            ),
        ]
        s = analytics_mod._summarise(pts)
        assert s.current_rate == 70.0
        assert s.best_day.date == "2025-01-02"
        assert s.worst_day.date == "2025-01-01"
        assert s.top_error_stage == "compliance"
