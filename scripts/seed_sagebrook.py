"""Seed data for Sagebrook Home — Phase 1 importer.

Creates:
- 1 Importer (Sagebrook Home)
- 1 ImporterProfile (logo, letter-spacing, handling symbols)
- 15 warning label templates
- 4 baseline compliance rules in DSL

Idempotent: safe to run multiple times.
"""
from __future__ import annotations

import json
import uuid
from typing import Any, Dict, List

# ── Constants ──────────────────────────────────────────────────────────────

TENANT_ID = "tnt-nakoda-001"
IMPORTER_ID = "imp-sagebrook-001"
IMPORTER_PROFILE_ID = "prof-sagebrook-001"

# ── Importer ───────────────────────────────────────────────────────────────

IMPORTER = {
    "id": IMPORTER_ID,
    "tenant_id": TENANT_ID,
    "name": "Sagebrook Home",
    "code": "SAGEBROOK",
    "country": "US",
    "contact_email": "imports@sagebrookhome.com",
    "contact_phone": "+1-562-555-0100",
    "status": "active",
}

# ── Importer Profile ──────────────────────────────────────────────────────

IMPORTER_PROFILE = {
    "id": IMPORTER_PROFILE_ID,
    "importer_id": IMPORTER_ID,
    "tenant_id": TENANT_ID,
    "logo_url": "s3://labelforge-artifacts/logos/sagebrook-home.svg",
    "brand_color": "#2C5F2D",
    "letter_spacing": 0.5,
    "font_family": "Helvetica Neue",
    "font_size_pt": 10,
    "handling_symbols": [
        {"symbol": "fragile", "svg_ref": "sym-fragile-001", "required": True},
        {"symbol": "this_side_up", "svg_ref": "sym-thisup-001", "required": True},
        {"symbol": "keep_dry", "svg_ref": "sym-keepdry-001", "required": False},
    ],
    "label_margin_mm": 3.0,
    "label_bleed_mm": 1.5,
}

# ── Warning Label Templates (15) ─────────────────────────────────────────

WARNING_LABELS: List[Dict[str, Any]] = [
    {
        "id": f"wl-sagebrook-{i:03d}",
        "tenant_id": TENANT_ID,
        "importer_id": IMPORTER_ID,
        "code": code,
        "title": title,
        "body_text": body,
        "severity": severity,
        "category": category,
        "applicable_markets": markets,
    }
    for i, (code, title, body, severity, category, markets) in enumerate([
        ("PROP65-LEAD", "California Prop 65 — Lead",
         "WARNING: This product can expose you to chemicals including lead, which is known to the State of California to cause cancer and birth defects.",
         "high", "chemical", ["US-CA"]),
        ("PROP65-WOOD", "California Prop 65 — Wood Dust",
         "WARNING: Drilling, sawing, sanding, or machining wood products can expose you to wood dust.",
         "medium", "chemical", ["US-CA"]),
        ("PROP65-GENERIC", "California Prop 65 — Generic",
         "WARNING: This product can expose you to chemicals known to the State of California to cause cancer.",
         "high", "chemical", ["US-CA"]),
        ("CPSIA-CHILD", "CPSIA Children's Product",
         "WARNING: CHOKING HAZARD — Small parts. Not for children under 3 years.",
         "high", "safety", ["US"]),
        ("FLAM-TEXTILE", "Flammability — Textile",
         "WARNING: This product meets flammability requirements of 16 CFR 1610.",
         "medium", "fire", ["US"]),
        ("ELEC-UL", "Electrical — UL Listed",
         "CAUTION: Risk of electric shock. Do not open. Refer servicing to qualified personnel.",
         "high", "electrical", ["US", "CA"]),
        ("GLASS-FRAG", "Glass — Fragile",
         "CAUTION: Contains glass components. Handle with care to avoid breakage and injury.",
         "medium", "physical", ["US", "EU", "CA"]),
        ("CANDLE-SAFE", "Candle Safety",
         "WARNING: Never leave a burning candle unattended. Keep away from flammable materials.",
         "high", "fire", ["US", "EU", "CA"]),
        ("FURN-TIP", "Furniture Tip-Over",
         "WARNING: Serious or fatal crushing injuries can occur from furniture tip-over. Anchor to wall.",
         "high", "safety", ["US"]),
        ("BATT-LITHIUM", "Lithium Battery",
         "CAUTION: Contains lithium battery. Do not dispose in fire or attempt to recharge.",
         "high", "chemical", ["US", "EU", "CA"]),
        ("CLEAN-CARE", "Cleaning and Care",
         "Clean with soft dry cloth only. Do not use abrasive cleaners or solvents.",
         "low", "care", ["US", "EU", "CA"]),
        ("OUTDOOR-UV", "Outdoor UV Warning",
         "NOTE: Prolonged exposure to direct sunlight may cause fading. Use in covered areas recommended.",
         "low", "care", ["US", "EU"]),
        ("WEIGHT-LIMIT", "Weight Limit",
         "CAUTION: Do not exceed maximum weight capacity. See product label for specific limits.",
         "medium", "safety", ["US", "EU", "CA"]),
        ("ALLERGY-NICKEL", "Nickel Allergy",
         "WARNING: This product contains nickel. May cause allergic reaction in sensitive individuals.",
         "medium", "chemical", ["EU"]),
        ("CE-MARK", "CE Conformity",
         "This product conforms to applicable EU directives and regulations.",
         "low", "compliance", ["EU"]),
    ], start=1)
]

# ── Compliance Rules (4 baseline, DSL format) ─────────────────────────────

COMPLIANCE_RULES: List[Dict[str, Any]] = [
    {
        "id": "rule-sagebrook-001",
        "tenant_id": TENANT_ID,
        "name": "California Prop 65 Required",
        "description": "All products shipped to California must include Prop 65 warning label",
        "severity": "block",
        "dsl": {
            "when": {
                "destination_state": {"in": ["CA"]},
                "country": {"eq": "US"},
            },
            "then": {
                "require_label": {"category": "chemical", "code_prefix": "PROP65"},
            },
            "priority": 100,
        },
        "status": "active",
    },
    {
        "id": "rule-sagebrook-002",
        "tenant_id": TENANT_ID,
        "name": "CPSIA for Children's Products",
        "description": "Products marketed for children under 12 must include CPSIA warning",
        "severity": "block",
        "dsl": {
            "when": {
                "product_category": {"in": ["children", "nursery", "kids_room"]},
                "country": {"eq": "US"},
            },
            "then": {
                "require_label": {"code": "CPSIA-CHILD"},
            },
            "priority": 90,
        },
        "status": "active",
    },
    {
        "id": "rule-sagebrook-003",
        "tenant_id": TENANT_ID,
        "name": "Furniture Tip-Over Warning",
        "description": "Freestanding furniture over 27 inches must include tip-over warning",
        "severity": "block",
        "dsl": {
            "when": {
                "product_category": {"in": ["furniture", "bookcase", "dresser", "cabinet"]},
                "height_inches": {"gt": 27},
                "country": {"eq": "US"},
            },
            "then": {
                "require_label": {"code": "FURN-TIP"},
                "require_anchor_kit": True,
            },
            "priority": 95,
        },
        "status": "active",
    },
    {
        "id": "rule-sagebrook-004",
        "tenant_id": TENANT_ID,
        "name": "EU CE Mark Required",
        "description": "All products entering the EU market must display CE marking",
        "severity": "warn",
        "dsl": {
            "when": {
                "destination_market": {"in": ["EU"]},
            },
            "then": {
                "require_label": {"code": "CE-MARK"},
            },
            "priority": 80,
        },
        "status": "active",
    },
]


def get_seed_data() -> Dict[str, Any]:
    """Return all seed data as a dictionary."""
    return {
        "importer": IMPORTER,
        "importer_profile": IMPORTER_PROFILE,
        "warning_labels": WARNING_LABELS,
        "compliance_rules": COMPLIANCE_RULES,
    }


def validate_seed_data() -> List[str]:
    """Validate seed data integrity. Returns list of errors (empty = valid)."""
    errors = []
    data = get_seed_data()

    if not data["importer"]["id"]:
        errors.append("Importer missing ID")

    profile = data["importer_profile"]
    if profile["importer_id"] != data["importer"]["id"]:
        errors.append("Profile importer_id mismatch")
    if not profile["logo_url"]:
        errors.append("Profile missing logo_url")
    if not profile["handling_symbols"]:
        errors.append("Profile missing handling_symbols")

    labels = data["warning_labels"]
    if len(labels) != 15:
        errors.append(f"Expected 15 warning labels, got {len(labels)}")

    label_codes = [l["code"] for l in labels]
    if len(set(label_codes)) != len(label_codes):
        errors.append("Duplicate warning label codes")

    rules = data["compliance_rules"]
    if len(rules) != 4:
        errors.append(f"Expected 4 compliance rules, got {len(rules)}")

    for rule in rules:
        if "when" not in rule["dsl"] or "then" not in rule["dsl"]:
            errors.append(f"Rule {rule['id']} missing when/then DSL")

    return errors


if __name__ == "__main__":
    errors = validate_seed_data()
    if errors:
        print("Validation errors:")
        for e in errors:
            print(f"  - {e}")
    else:
        data = get_seed_data()
        print(f"Seed data valid:")
        print(f"  Importer: {data['importer']['name']}")
        print(f"  Profile: logo={data['importer_profile']['logo_url']}")
        print(f"  Warning labels: {len(data['warning_labels'])}")
        print(f"  Compliance rules: {len(data['compliance_rules'])}")
        print(json.dumps(data, indent=2, default=str))
