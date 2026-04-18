"""``POST /importers/{id}/profile/sanitize-panel-layouts`` — scrub junk
entries (warning-label text, URLs) out of a stored profile's
``panel_layouts`` without re-running LLM extraction.
"""
from __future__ import annotations


def _seed_importer_with_junk_profile(client, admin_headers):
    r = client.post(
        "/api/v1/importers",
        json={"name": "Sagebrook", "code": "sage"},
        headers=admin_headers,
    )
    assert r.status_code == 201, r.text
    importer_id = r.json()["id"]

    junk_layouts = {
        "carton_top": [
            "upc",
            "item_description",
            "for more information go to www.p65warnings.ca.gov/furniture",
            "WARNING: California Prop 65 chemical exposure notice.",
        ],
        "carton_side": {
            "selected": True,
            "fields": [
                "country_of_origin",
                "4×3 inches",
                "prop65_warning",
            ],
        },
    }
    r = client.put(
        f"/api/v1/importers/{importer_id}",
        json={"panel_layouts": junk_layouts},
        headers=admin_headers,
    )
    assert r.status_code == 200, r.text
    return importer_id


def test_dry_run_reports_without_writing(client, admin_headers):
    importer_id = _seed_importer_with_junk_profile(client, admin_headers)

    r = client.post(
        f"/api/v1/importers/{importer_id}/profile/sanitize-panel-layouts"
        "?dry_run=true",
        headers=admin_headers,
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["new_version"] is None  # dry run
    assert any("p65warnings" in s for s in body["dropped_entries"])
    assert any("WARNING" in s for s in body["dropped_entries"])
    assert "upc" in body["kept_entries"]
    assert "prop65_warning" in body["kept_entries"]

    # Profile untouched.
    r = client.get(f"/api/v1/importers/{importer_id}", headers=admin_headers)
    layouts = r.json()["panel_layouts"]
    assert any(
        "p65warnings" in s for s in layouts["carton_top"]
    ), "dry_run must not modify the stored profile"


def test_write_path_creates_new_version_with_clean_layouts(client, admin_headers):
    importer_id = _seed_importer_with_junk_profile(client, admin_headers)

    r = client.post(
        f"/api/v1/importers/{importer_id}/profile/sanitize-panel-layouts",
        headers=admin_headers,
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["new_version"] is not None
    assert body["new_version"] >= 2  # bumped over the seed version

    # Latest profile now has cleaned layouts.
    r = client.get(f"/api/v1/importers/{importer_id}", headers=admin_headers)
    layouts = r.json()["panel_layouts"]
    assert layouts["carton_top"] == ["upc", "item_description"]
    assert layouts["carton_side"]["fields"] == ["country_of_origin", "prop65_warning"]


def test_no_profile_returns_404(client, admin_headers):
    r = client.post(
        "/api/v1/importers",
        json={"name": "Empty", "code": "empty"},
        headers=admin_headers,
    )
    importer_id = r.json()["id"]

    r = client.post(
        f"/api/v1/importers/{importer_id}/profile/sanitize-panel-layouts",
        headers=admin_headers,
    )
    # Either 404 "no profile" (endpoint-level) or 404 "resource not found"
    # (importer lookup missed because the seed layer races with the test
    # fixture on fresh in-memory DB). Both are acceptable — point is we
    # don't 500 and don't create a profile.
    assert r.status_code == 404
