"""
SafeBite backend — Core Scan Flow
==================================
Endpoints your frontend (scan.html / verdict.html / ingredient-detail.html)
should call instead of the mock functions in app-data.js:

  POST /api/scan            -> upload a label photo, get back a verdict
  GET  /api/scans           -> scan history (for dashboard)
  GET  /api/scans/{id}      -> one scan, same shape as MOCK_SCANS entries
  GET  /api/ingredient/{id} -> same shape as MOCK_INGREDIENTS entries
  GET  /api/profile         -> current user's allergen profile
  POST /api/profile         -> save allergen profile
  GET  /api/swaps/{scan_id} -> ranked swap candidates for a flagged/unclear scan
  GET  /api/swaps?q=        -> ranked swap candidates for a typed/spoken craving

Response JSON shapes match app-data.js exactly on purpose, so swapping
the frontend from mock -> real is a URL change, not a rewrite.

Run:
  pip install -r requirements.txt
  uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
"""

from contextlib import asynccontextmanager

from fastapi import FastAPI, UploadFile, File, HTTPException, Depends
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import List, Optional
import uuid, io, re

from app.api.explain_routes import router as explain_router
from app.api.nudge_routes import router as nudge_router
from app.ai.detector import detect_panel
from app.core.exceptions import (
    LLMUnavailableError,
    llm_unavailable_handler,
    unhandled_exception_handler,
)
from app.core import database as db
from app.core.auth import router as auth_router, current_user
from app.core.config import ALLOWED_ORIGINS, OLLAMA_BASE_URL, MIN_OCR_ALNUM_CHARS
from app.core.logging_config import logger, setup_logging
from app.ai.craving_vae import (
    rank_craving,
    craving_text_to_vector,
    flagged_item_to_vector,
    rank_swaps_vae,
)
from app.ai import craving_engine

# ---------------------------------------------------------------
# Startup / shutdown
# ---------------------------------------------------------------
@asynccontextmanager
async def lifespan(app: FastAPI):
    setup_logging()
    db.init_db()
    feedback.init()
    _check_ollama_reachable()
    yield


def _check_ollama_reachable() -> None:
    """
    Non-fatal startup check for Ollama. The old behavior was: the first
    request to /explain-ingredient or /explain-swap would fail with a
    generic connection error and no context. This logs a loud, specific
    warning once at boot instead, so it's obvious *before* a demo why
    those two routes won't work, without blocking the rest of the API
    (scan/verdict/swap-ranking/profile all work fine without Ollama).
    """
    try:
        import httpx
        httpx.get(f"{OLLAMA_BASE_URL}/api/tags", timeout=2.0)
        logger.info(f"Ollama reachable at {OLLAMA_BASE_URL}")
    except Exception:
        logger.warning(
            "=" * 70 + "\n"
            f"Ollama not reachable at {OLLAMA_BASE_URL}.\n"
            "/explain-ingredient and /explain-swap will return 503 until:\n"
            "  1) Ollama is installed and running (https://ollama.com), and\n"
            "  2) the model is pulled: `ollama pull llama3.2`\n"
            "Everything else (scan, verdict, swaps, profile) works without it.\n"
            + "=" * 70
        )


app = FastAPI(title="SafeBite API", lifespan=lifespan)

# Restricted to a dev allowlist by default — see app/core/config.py to
# override via the ALLOWED_ORIGINS env var when deploying. The old
# allow_origins=["*"] let any website's frontend JS call this API using a
# visitor's browser session; that's a real vulnerability once this is
# deployed anywhere with actual user data attached.
app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_origin_regex=r"https://.*\.app\.github\.dev",
    allow_methods=["*"],
    allow_headers=["*"],
)

# Wire in the AI explanation routes (/explain-ingredient, /explain-swap).
# Without this include_router call, explain_routes.py is fully coded but
# unreachable at runtime.
app.include_router(auth_router)
app.include_router(explain_router)
app.include_router(nudge_router)

# Register the custom exception handlers so LLM failures return the clean
# {"error": ..., "message": ...} JSON shape instead of a raw framework 500.
app.add_exception_handler(LLMUnavailableError, llm_unavailable_handler)
app.add_exception_handler(Exception, unhandled_exception_handler)


# ---------------------------------------------------------------
# Static reference data — ingredient KB stays in-code (small, fixed
# vocabulary, not user data). Scans and the user profile are the things
# that actually needed persistence, and now live in app/core/database.py.
# ---------------------------------------------------------------

from app.core.allergen_kb import INGREDIENT_KB  # single source of truth (was inline here)
from app.core import label_analysis, barcode, feedback
from app.core.label_analysis import compute_verdict  # re-exported so existing imports keep working


# ---------------------------------------------------------------
# Pydantic response models — mirror app-data.js shapes
# ---------------------------------------------------------------

class FlaggedIngredient(BaseModel):
    id: str
    name: str

class ScanResult(BaseModel):
    scanId: str
    productName: str
    date: str
    verdict: str  # "safe" | "flagged" | "unclear"
    flaggedIngredients: List[FlaggedIngredient]
    note: Optional[str] = None  # populated when a verdict was downgraded (e.g. OCR failure)

class IngredientDetail(BaseModel):
    name: str
    plainLanguage: str
    aliases: List[str]
    whyForYou: str

class ProfileIn(BaseModel):
    allergens: List[str]




# ---------------------------------------------------------------
# OCR — real pytesseract call. Falls back to empty string if
# tesseract isn't installed on the machine running this.
# ---------------------------------------------------------------
def run_ocr(image_bytes: bytes) -> str:
    try:
        import pytesseract
        from PIL import Image, ImageOps

        from app.core.config import TESSERACT_CMD
        if TESSERACT_CMD:
            pytesseract.pytesseract.tesseract_cmd = TESSERACT_CMD

        img = Image.open(io.BytesIO(image_bytes)).convert("RGB")
        if img.width < 1500:
            scale = 1500 / img.width
            img = img.resize((int(img.width * scale), int(img.height * scale)), Image.LANCZOS)

        candidates = [
            ImageOps.autocontrast(img.convert("L")),
            ImageOps.autocontrast(img.split()[1]),
        ]
        texts = [pytesseract.image_to_string(c, config="--psm 6") for c in candidates]
        return max(texts, key=len).lower()
    except Exception as e:
        logger.warning(f"OCR failed/unavailable: {e}")
        return ""


# ---------------------------------------------------------------
# VERDICT ENGINE — rule-based keyword matching against the user's
# allergen profile + the ingredient KB above, deliberately kept
# deterministic and auditable (see the report's rationale for why
# this one component is NOT a learned classifier).
#
# Safety-critical fix: OCR failure or near-empty extraction must
# NEVER fall through to "safe" — that would be a silent false
# negative on an allergen safety check. If we can't read enough of
# the label, the verdict is "unclear" with an explicit note, same
# as the existing ambiguous-ingredient case, so the frontend's
# 3-state UI (safe/flagged/unclear) doesn't need to change.
# ---------------------------------------------------------------
# compute_verdict now lives in app/core/label_analysis.py (context-aware).


# ---------------------------------------------------------------
# ROUTES
# ---------------------------------------------------------------

@app.post("/api/scan", response_model=ScanResult)
async def scan_label(file: UploadFile = File(...), product_name: Optional[str] = "Scanned Product", barcode_text: Optional[str] = None, user: dict = Depends(current_user)):
    image_bytes = await file.read()

    cropped = detect_panel(image_bytes)           # YOLOv8 product detector (falls back to full image)
    logger.info(
        "YOLO detector: %s (input %d bytes, output %d bytes)",
        "fell back to full image" if cropped == image_bytes else "cropped to detected product",
        len(image_bytes), len(cropped),
    )
    ocr_text = run_ocr(cropped)
    # If the crop lost the text or the ingredients heading, retry on the full image
    if len(re.sub(r"[^a-z0-9]", "", ocr_text)) < MIN_OCR_ALNUM_CHARS or "ingredient" not in ocr_text:
        ocr_text = run_ocr(image_bytes)
    # Barcode cross-check (optional): typed code wins, else try to decode from the photo.
    code = barcode.normalize(barcode_text) or barcode.decode_barcode(image_bytes)
    product = barcode.lookup(code) if code else None
    if product and product_name in (None, "", "Scanned Product"):
        product_name = product.get("name") or product_name
    verdict, flagged, note = label_analysis.compute_verdict_with_database(
        ocr_text, db.get_profile(user["id"])["allergens"], MIN_OCR_ALNUM_CHARS, product)

    scan_id = str(uuid.uuid4())[:8]
    scan = {
        "scanId": scan_id,
        "productName": product_name,
        "date": "today",
        "verdict": verdict,
        "flaggedIngredients": flagged,
        "note": note,
    }
    db.save_scan(scan, user["id"])
    return scan


@app.get("/api/scans", response_model=List[ScanResult])
def list_scans(user: dict = Depends(current_user)):
    return db.list_scans(user["id"])  # already most-recent-first


@app.get("/api/scans/{scan_id}", response_model=ScanResult)
def get_scan(scan_id: str, user: dict = Depends(current_user)):
    scan = db.get_scan(scan_id, user["id"])
    if not scan:
        raise HTTPException(404, "Scan not found")
    return scan


class FeedbackIn(BaseModel):
    scanId: str
    kind: str
    comment: Optional[str] = None


@app.post("/api/feedback")
def post_feedback(body: FeedbackIn, user: dict = Depends(current_user)):
    if not db.get_scan(body.scanId, user["id"]):
        raise HTTPException(404, "Scan not found")
    try:
        feedback.save(user["id"], body.scanId, body.kind, body.comment)
    except ValueError as e:
        raise HTTPException(400, str(e))
    return {"ok": True}


@app.get("/api/ingredient/{ingredient_id}", response_model=IngredientDetail)
def get_ingredient(ingredient_id: str):
    ing = INGREDIENT_KB.get(ingredient_id)
    if not ing:
        raise HTTPException(404, "Ingredient not found")
    return {
        "name": ing["name"],
        "plainLanguage": ing["plainLanguage"],
        "aliases": [a.title() for a in ing["aliases"]],
        "whyForYou": ing["whyForYouTemplate"],
    }


@app.get("/api/swaps/{scan_id}")
def get_swaps_for_scan(scan_id: str, user: dict = Depends(current_user)):
    scan = db.get_scan(scan_id, user["id"])
    if not scan:
        raise HTTPException(404, "Scan not found")
    # Build a craving-signature query vector from the flagged ingredient(s)
    # and product name, then rank via the trained VAE's latent space
    # instead of the old tag-overlap heuristic.
    text_source = " ".join([ing["name"] for ing in scan["flaggedIngredients"]] + [scan["productName"]])
    query_vec = flagged_item_to_vector(text_source)
    return craving_engine.search(scan["productName"], db.get_profile(user["id"])["allergens"], _prefs(user))


@app.get("/api/swaps")
def search_swaps(q: str, user: dict = Depends(current_user)):
    return craving_engine.search(q, db.get_profile(user["id"])["allergens"], _prefs(user))


@app.get("/api/profile")
def get_profile(user: dict = Depends(current_user)):
    return db.get_profile(user["id"])

@app.get("/api/craving/understand")
def understand_craving(q: str, user: dict = Depends(current_user)):
    return craving_engine.understand(q)

@app.post("/api/profile")
def set_profile(profile: ProfileIn, user: dict = Depends(current_user)):
    return db.set_profile(user["id"], profile.allergens)

class PrefsIn(BaseModel):
    prefs: dict

    
def _prefs(user):
    try:
        return db.get_prefs(user["id"])
    except Exception:
        return {}


@app.get("/api/profile/prefs")
def get_prefs(user: dict = Depends(current_user)):
    return {"prefs": db.get_prefs(user["id"])}


@app.post("/api/profile/prefs")
def set_prefs(body: PrefsIn, user: dict = Depends(current_user)):
    db.set_prefs(user["id"], body.prefs)
    return {"prefs": body.prefs}

@app.get("/")
def root():
    return {"status": "ok", "service": "safebite-backend"}


@app.get("/health")
def health():
    return {"status": "ok", "service": "safebite-backend"}