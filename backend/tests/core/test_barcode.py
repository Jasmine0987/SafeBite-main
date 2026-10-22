from app.core import barcode


def test_valid_gtin():
    assert barcode.valid_gtin("4006381333931")      # EAN-13
    assert barcode.valid_gtin("96385074")           # EAN-8
    assert barcode.valid_gtin("036000291452")       # UPC-A
    assert not barcode.valid_gtin("4006381333932")  # bad check digit
    assert not barcode.valid_gtin("12345") and not barcode.valid_gtin("abc")


def test_normalize_strips_noise():
    assert barcode.normalize(" 4006381333931 ") == "4006381333931"
    assert barcode.normalize("1234") is None and barcode.normalize(None) is None


def test_parse_off_maps_allergens():
    payload = {"status": 1, "product": {
        "code": "4006381333931", "product_name": " Choco Bar ", "brands": "Acme, Other",
        "ingredients_text": "sugar, milk", "allergens_tags": ["en:milk", "en:gluten", "en:nuts"],
        "traces_tags": ["en:peanuts"]}}
    p = barcode._parse_off(payload)
    assert p["name"] == "Choco Bar" and p["brand"] == "Acme"
    assert set(p["allergen_ids"]) == {"milk", "wheat", "gluten", "tree-nut"}
    assert p["trace_ids"] == ["peanut"]


def test_parse_off_not_found_or_error():
    assert barcode._parse_off({"status": 0}) is None
    assert barcode._parse_off(None) is None


def test_lookup_uses_fetch_and_survives_network_failure(monkeypatch):
    barcode.lookup.cache_clear()
    monkeypatch.setattr(barcode, "_fetch_json", lambda url: None)
    assert barcode.lookup("4006381333931") is None
    barcode.lookup.cache_clear()
    monkeypatch.setattr(barcode, "_fetch_json", lambda url: {"status": 1, "product": {"product_name": "X"}})
    assert barcode.lookup("4006381333931")["name"] == "X"
    assert barcode.lookup("123") is None  # invalid code never hits the network


def test_decode_generated_ean13():
    import io
    try:
        import barcode as pybarcode
        from barcode.writer import ImageWriter
    except Exception:
        import pytest
        pytest.skip("python-barcode not installed")
    buf = io.BytesIO()
    pybarcode.get("ean13", "400638133393", writer=ImageWriter()).write(buf)
    got = barcode.decode_barcode(buf.getvalue())
    if got is None:
        import pytest
        pytest.skip("no barcode decoder available (install pyzbar + libzbar0 or OpenCV >= 4.8)")
    assert got == "4006381333931"
