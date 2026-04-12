"""Tests for Sagebrook Home seed data."""
from __future__ import annotations

import pytest
from scripts.seed_sagebrook import (
    COMPLIANCE_RULES,
    IMPORTER,
    IMPORTER_ID,
    IMPORTER_PROFILE,
    IMPORTER_PROFILE_ID,
    TENANT_ID,
    WARNING_LABELS,
    get_seed_data,
    validate_seed_data,
)


# ── Importer ─────────────────────────────────────────────────────────────

class TestImporter:
    def test_importer_id(self):
        assert IMPORTER["id"] == IMPORTER_ID

    def test_importer_tenant(self):
        assert IMPORTER["tenant_id"] == TENANT_ID

    def test_importer_name(self):
        assert IMPORTER["name"] == "Sagebrook Home"

    def test_importer_code(self):
        assert IMPORTER["code"] == "SAGEBROOK"

    def test_importer_country(self):
        assert IMPORTER["country"] == "US"

    def test_importer_status(self):
        assert IMPORTER["status"] == "active"

    def test_importer_has_contact(self):
        assert IMPORTER["contact_email"]
        assert IMPORTER["contact_phone"]


# ── Importer Profile ─────────────────────────────────────────────────────

class TestImporterProfile:
    def test_profile_links_to_importer(self):
        assert IMPORTER_PROFILE["importer_id"] == IMPORTER_ID

    def test_profile_tenant(self):
        assert IMPORTER_PROFILE["tenant_id"] == TENANT_ID

    def test_profile_has_logo(self):
        assert IMPORTER_PROFILE["logo_url"].startswith("s3://")

    def test_profile_letter_spacing(self):
        assert isinstance(IMPORTER_PROFILE["letter_spacing"], (int, float))
        assert IMPORTER_PROFILE["letter_spacing"] >= 0

    def test_profile_font_settings(self):
        assert IMPORTER_PROFILE["font_family"]
        assert IMPORTER_PROFILE["font_size_pt"] > 0

    def test_profile_handling_symbols_count(self):
        symbols = IMPORTER_PROFILE["handling_symbols"]
        assert len(symbols) == 3

    def test_profile_handling_symbols_structure(self):
        for sym in IMPORTER_PROFILE["handling_symbols"]:
            assert "symbol" in sym
            assert "svg_ref" in sym
            assert "required" in sym

    def test_profile_label_margins(self):
        assert IMPORTER_PROFILE["label_margin_mm"] > 0
        assert IMPORTER_PROFILE["label_bleed_mm"] > 0


# ── Warning Labels ────────────────────────────────────────────────────────

class TestWarningLabels:
    def test_label_count(self):
        assert len(WARNING_LABELS) == 15

    def test_label_ids_unique(self):
        ids = [l["id"] for l in WARNING_LABELS]
        assert len(set(ids)) == 15

    def test_label_codes_unique(self):
        codes = [l["code"] for l in WARNING_LABELS]
        assert len(set(codes)) == 15

    def test_labels_linked_to_importer(self):
        for label in WARNING_LABELS:
            assert label["importer_id"] == IMPORTER_ID
            assert label["tenant_id"] == TENANT_ID

    def test_label_required_fields(self):
        for label in WARNING_LABELS:
            assert label["code"]
            assert label["title"]
            assert label["body_text"]
            assert label["severity"] in ("low", "medium", "high")
            assert label["category"]
            assert len(label["applicable_markets"]) > 0

    def test_prop65_labels_target_california(self):
        prop65 = [l for l in WARNING_LABELS if l["code"].startswith("PROP65")]
        assert len(prop65) == 3
        for label in prop65:
            assert "US-CA" in label["applicable_markets"]

    def test_cpsia_label_exists(self):
        cpsia = [l for l in WARNING_LABELS if l["code"] == "CPSIA-CHILD"]
        assert len(cpsia) == 1
        assert cpsia[0]["severity"] == "high"

    def test_ce_mark_targets_eu(self):
        ce = [l for l in WARNING_LABELS if l["code"] == "CE-MARK"]
        assert len(ce) == 1
        assert "EU" in ce[0]["applicable_markets"]

    def test_severity_distribution(self):
        severities = [l["severity"] for l in WARNING_LABELS]
        assert "high" in severities
        assert "medium" in severities
        assert "low" in severities

    def test_categories_present(self):
        categories = {l["category"] for l in WARNING_LABELS}
        assert "chemical" in categories
        assert "safety" in categories
        assert "fire" in categories


# ── Compliance Rules ──────────────────────────────────────────────────────

class TestComplianceRules:
    def test_rule_count(self):
        assert len(COMPLIANCE_RULES) == 4

    def test_rule_ids_unique(self):
        ids = [r["id"] for r in COMPLIANCE_RULES]
        assert len(set(ids)) == 4

    def test_rules_linked_to_tenant(self):
        for rule in COMPLIANCE_RULES:
            assert rule["tenant_id"] == TENANT_ID

    def test_rules_have_dsl(self):
        for rule in COMPLIANCE_RULES:
            dsl = rule["dsl"]
            assert "when" in dsl
            assert "then" in dsl
            assert "priority" in dsl

    def test_rules_have_severity(self):
        for rule in COMPLIANCE_RULES:
            assert rule["severity"] in ("block", "warn")

    def test_rules_all_active(self):
        for rule in COMPLIANCE_RULES:
            assert rule["status"] == "active"

    def test_prop65_rule_targets_california(self):
        rule = next(r for r in COMPLIANCE_RULES if r["id"] == "rule-sagebrook-001")
        assert rule["dsl"]["when"]["destination_state"]["in"] == ["CA"]

    def test_furniture_rule_height_threshold(self):
        rule = next(r for r in COMPLIANCE_RULES if r["id"] == "rule-sagebrook-003")
        assert rule["dsl"]["when"]["height_inches"]["gt"] == 27

    def test_rule_priorities_distinct(self):
        priorities = [r["dsl"]["priority"] for r in COMPLIANCE_RULES]
        assert len(set(priorities)) == 4


# ── Helper Functions ──────────────────────────────────────────────────────

class TestHelpers:
    def test_get_seed_data_keys(self):
        data = get_seed_data()
        assert set(data.keys()) == {"importer", "importer_profile", "warning_labels", "compliance_rules"}

    def test_get_seed_data_types(self):
        data = get_seed_data()
        assert isinstance(data["importer"], dict)
        assert isinstance(data["importer_profile"], dict)
        assert isinstance(data["warning_labels"], list)
        assert isinstance(data["compliance_rules"], list)

    def test_validate_seed_data_passes(self):
        errors = validate_seed_data()
        assert errors == []

    def test_validate_detects_label_count_mismatch(self, monkeypatch):
        import scripts.seed_sagebrook as mod
        original = mod.WARNING_LABELS
        monkeypatch.setattr(mod, "WARNING_LABELS", original[:5])
        errors = validate_seed_data()
        assert any("15" in e for e in errors)

    def test_validate_detects_rule_count_mismatch(self, monkeypatch):
        import scripts.seed_sagebrook as mod
        original = mod.COMPLIANCE_RULES
        monkeypatch.setattr(mod, "COMPLIANCE_RULES", original[:2])
        errors = validate_seed_data()
        assert any("4" in e for e in errors)
