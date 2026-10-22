"""
Barcode decoding + Open Food Facts lookup, used to cross-check a photo scan.

* decode_barcode(image_bytes) tries pyzbar (needs `apt install libzbar0` + `pip install pyzbar`),
  then OpenCV's built-in barcode detector. Both are optional; if neither works the
  user can type the barcode and the scan still runs.
* lookup(code) queries Open Food Facts (free, crowd-sourced). Data can be wrong or
  outdated, so label_analysis only lets it ESCALATE a verdict, never lower it.
* Network failures return None. A scan never fails because the database is down.
"""
from __future__ import annotations

import io
import re
from functools import lru_cache
from typing import Dict, List, Optional

OFF_URL = "https://world.openfoodfacts.org/api/v2/product/{code}.json"
OFF_FIELDS = "code,product_name,brands,ingredients_text,allergens_tags,traces_tags"
USER_AGENT = "SafeBite/0.1 (student project; allergen label cross-check)"

# Open Food Facts allergen tags -> knowledge-base ids
_OFF_TO_KB: Dict[str, List[str]] = {
    "en:milk": ["milk"], "en:eggs": ["egg"], "en:fish": ["fish"],
    "en:crustaceans": ["shellfish"], "en:molluscs": ["shellfish"],
    "en:nuts": ["tree-nut"], "en:peanuts": ["peanut"],
    "en:gluten": ["wheat", "gluten"],  # gluten may be barley/rye: escalate for both
    "en:soybeans": ["soy"], "en:sesame-seeds": ["sesame"],
}


def valid_gtin(code: str) -> bool:
    """EAN-8 / UPC-A / EAN-13 / GTIN-14 length + check-digit validation."""
    if not code or not code.isdigit() or len(code) not in (8, 12, 13, 14):
        return False
    digits = [int(c) for c in code]
    body, check = digits[:-1], digits[-1]
    total = sum(d * (3 if i % 2 == 0 else 1) for i, d in enumerate(reversed(body)))
    return (10 - total % 10) % 10 == check


def normalize(code: Optional[str]) -> Optional[str]:
    if not code:
        return None
    digits = re.sub(r"\D", "", str(code))
    return digits if valid_gtin(digits) else None


def decode_barcode(image_bytes: bytes) -> Optional[str]:
    try:
        from PIL import Image
        img = Image.open(io.BytesIO(image_bytes)).convert("RGB")
    except Exception:
        return None

    try:  # 1) pyzbar
        from pyzbar.pyzbar import decode
        for r in decode(img):
            code = normalize(r.data.decode("ascii", "ignore"))
            if code:
                return code
    except Exception:
        pass

    try:  # 2) OpenCV (>=4.8 ships a barcode detector)
        import cv2
        import numpy as np
        arr = cv2.cvtColor(np.array(img), cv2.COLOR_RGB2BGR)
        det = cv2.barcode.BarcodeDetector() if hasattr(cv2, "barcode") else cv2.barcode_BarcodeDetector()
        out = det.detectAndDecode(arr)
        infos = out[1] if len(out) >= 3 and isinstance(out[0], bool) else out[0]
        if isinstance(infos, str):
            infos = [infos]
        for info in infos or []:
            code = normalize(info)
            if code:
                return code
    except Exception:
        pass
    return None


def _fetch_json(url: str) -> Optional[dict]:
    try:
        import httpx
        r = httpx.get(url, params={"fields": OFF_FIELDS}, timeout=4.0,
                      headers={"User-Agent": USER_AGENT})
        if r.status_code != 200:
            return None
        return r.json()
    except Exception:
        return None


def _parse_off(payload: Optional[dict]) -> Optional[dict]:
    if not payload or payload.get("status") != 1:
        return None
    p = payload.get("product") or {}

    def ids(tags):
        out: List[str] = []
        for t in tags or []:
            out += _OFF_TO_KB.get(str(t).lower(), [])
        return sorted(set(out))

    return {
        "code": p.get("code"),
        "name": (p.get("product_name") or "").strip() or None,
        "brand": (p.get("brands") or "").split(",")[0].strip() or None,
        "ingredients_text": p.get("ingredients_text") or None,
        "allergen_ids": ids(p.get("allergens_tags")),
        "trace_ids": ids(p.get("traces_tags")),
        "source": "Open Food Facts",
    }


@lru_cache(maxsize=256)
def lookup(code: str) -> Optional[dict]:
    code = normalize(code)
    if not code:
        return None
    return _parse_off(_fetch_json(OFF_URL.format(code=code)))
