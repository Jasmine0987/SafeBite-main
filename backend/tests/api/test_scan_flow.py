"""
Core scan-flow coverage: /api/scan, /api/scans, /api/swaps, /api/profile.

Previously untested — the only route tests that existed were for
/explain-ingredient and /explain-swap, which aren't the core product flow.
This file also directly locks in the OCR-failure-safety fix: a scan with
no readable text must NEVER come back "safe".
"""

import io
import uuid

import pytest

from app.main import compute_verdict, MIN_OCR_ALNUM_CHARS



# ---------------------------------------------------------------------------
# compute_verdict — unit-level, no HTTP needed
# ---------------------------------------------------------------------------

def test_verdict_safe_on_clean_label_with_no_flagged_ingredients():
    verdict, flagged, note = compute_verdict("ingredients: water, sugar, salt, citric acid", [])
    assert verdict == "safe"
    assert flagged == []
    assert note is None


def test_verdict_flagged_when_allergen_on_profile():
    verdict, flagged, note = compute_verdict("ingredients: wheat flour, peanuts, salt", ["peanut"])
    assert verdict == "flagged"
    assert flagged == [{"id": "peanut", "name": "Peanut"}]


def test_verdict_unclear_on_ambiguous_ingredient():
    verdict, flagged, note = compute_verdict("ingredients: sugar, natural flavoring, salt", [])
    assert verdict == "unclear"
    assert flagged == []
    assert note is not None


def test_verdict_never_silently_safe_on_empty_ocr_text():
    """
    The core safety fix: empty OCR output must not produce a false "safe".
    """
    verdict, flagged, note = compute_verdict("", ["peanut"])
    assert verdict == "unclear"
    assert flagged == []
    assert note is not None
    assert "couldn't read" in note.lower() or "could not read" in note.lower() or "read enough" in note.lower()


def test_verdict_never_silently_safe_on_near_empty_ocr_text():
    """
    A couple of stray characters (e.g. a barcode digit OCR half-caught)
    shouldn't be enough to run the verdict engine either.
    """
    short_text = "a1"
    assert len(short_text) < MIN_OCR_ALNUM_CHARS
    verdict, flagged, note = compute_verdict(short_text, ["peanut"])
    assert verdict == "unclear"


def test_verdict_runs_normally_once_enough_text_present():
    # Sanity check that the threshold doesn't block real labels.
    long_text = "ingredients: enriched wheat flour, sugar, palm oil, salt, baking soda"
    assert len(long_text) >= MIN_OCR_ALNUM_CHARS
    verdict, flagged, note = compute_verdict(long_text, [])
    assert verdict == "safe"


# ---------------------------------------------------------------------------
# Auth helper: every data route now needs a logged-in user
# ---------------------------------------------------------------------------

@pytest.fixture
def auth(client):
    """Sign up a fresh user and attach its bearer token to the test client."""
    email = f"test-{uuid.uuid4().hex[:8]}@example.com"
    r = client.post("/api/auth/signup", json={"email": email, "password": "password123"})
    assert r.status_code == 200, r.text
    client.headers.update({"Authorization": f"Bearer {r.json()['token']}"})
    return client


def _fake_image_bytes() -> bytes:
    # Doesn't need to be a real image: OCR fails and returns "", which is
    # exactly the unreadable-label path we want to exercise.
    return b"not a real image"


def _make_scan(c, name="Mystery Snack"):
    files = {"file": ("label.jpg", io.BytesIO(_fake_image_bytes()), "image/jpeg")}
    return c.post("/api/scan", files=files, params={"product_name": name})


# ---------------------------------------------------------------------------
# /api/scan
# ---------------------------------------------------------------------------

def test_scan_requires_login(client):
    client.headers.pop("Authorization", None)
    assert _make_scan(client).status_code == 401


def test_scan_endpoint_with_unreadable_image_returns_unclear_not_safe(auth):
    response = _make_scan(auth)
    assert response.status_code == 200
    body = response.json()
    assert body["verdict"] == "unclear"  # never "safe" on garbage input
    assert body["note"]


def test_scan_endpoint_persists_and_is_retrievable(auth):
    created = _make_scan(auth, "Persisted Snack").json()
    fetched = auth.get(f"/api/scans/{created['scanId']}")
    assert fetched.status_code == 200
    assert fetched.json()["productName"] == "Persisted Snack"


def test_scan_not_found_returns_404(auth):
    assert auth.get("/api/scans/does-not-exist").status_code == 404


def test_list_scans_returns_only_this_users_scans(auth):
    assert auth.get("/api/scans").json() == []
    created = _make_scan(auth, "Mine").json()
    ids = [s["scanId"] for s in auth.get("/api/scans").json()]
    assert ids == [created["scanId"]]


def test_scan_accepts_barcode_text_without_crashing(auth):
    files = {"file": ("label.jpg", io.BytesIO(_fake_image_bytes()), "image/jpeg")}
    r = auth.post("/api/scan", files=files, params={"barcode_text": "4006381333931"})
    assert r.status_code == 200
    assert r.json()["verdict"] != "safe"  # unreadable photo must never become "safe"


# ---------------------------------------------------------------------------
# /api/feedback
# ---------------------------------------------------------------------------

def test_feedback_saves_for_own_scan(auth):
    scan = _make_scan(auth).json()
    r = auth.post("/api/feedback", json={"scanId": scan["scanId"], "kind": "missed_allergen", "comment": "had milk"})
    assert r.status_code == 200 and r.json() == {"ok": True}


def test_feedback_rejects_bad_kind_and_unknown_scan(auth):
    scan = _make_scan(auth).json()
    assert auth.post("/api/feedback", json={"scanId": scan["scanId"], "kind": "nonsense"}).status_code == 400
    assert auth.post("/api/feedback", json={"scanId": "nope", "kind": "other"}).status_code == 404


# ---------------------------------------------------------------------------
# /api/swaps
# ---------------------------------------------------------------------------

def test_search_swaps_by_craving_query_returns_results(auth):
    response = auth.get("/api/swaps", params={"q": "something crunchy and salty"})
    assert response.status_code == 200
    body = response.json()
    assert body["results"]


def test_search_swaps_requires_query_param(auth):
    assert auth.get("/api/swaps").status_code == 422


def test_swaps_for_scan_returns_results(auth):
    scan = _make_scan(auth, "Crunchy Chips").json()
    response = auth.get(f"/api/swaps/{scan['scanId']}")
    assert response.status_code == 200
    assert response.json()["results"]


def test_swaps_for_nonexistent_scan_returns_404(auth):
    assert auth.get("/api/swaps/does-not-exist").status_code == 404


def test_swaps_never_contain_a_profile_allergen(auth):
    auth.post("/api/profile", json={"allergens": ["peanut", "dairy"]})
    for r in auth.get("/api/swaps", params={"q": "chocolate snack"}).json()["results"]:
        assert not ({"peanut", "dairy"} & set(r["allergens"]))


# ---------------------------------------------------------------------------
# /api/profile
# ---------------------------------------------------------------------------

def test_get_profile_returns_allergens_list(auth):
    response = auth.get("/api/profile")
    assert response.status_code == 200
    assert "allergens" in response.json()


def test_set_profile_persists(auth):
    r = auth.post("/api/profile", json={"allergens": ["peanut", "dairy"]})
    assert r.status_code == 200
    assert auth.get("/api/profile").json()["allergens"] == ["peanut", "dairy"]