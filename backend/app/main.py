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

from fastapi import FastAPI, UploadFile, File, HTTPException
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
from app.core.config import ALLOWED_ORIGINS, OLLAMA_BASE_URL, MIN_OCR_ALNUM_CHARS
from app.core.logging_config import logger, setup_logging
from app.ai.craving_vae import (
    craving_text_to_vector,
    flagged_item_to_vector,
    rank_swaps_vae,
)


# ---------------------------------------------------------------
# Startup / shutdown
# ---------------------------------------------------------------
@asynccontextmanager
async def lifespan(app: FastAPI):
    setup_logging()
    db.init_db()
    db.seed_demo_scans_if_empty()
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

def _entry(name, aliases, tags, plain, why):
    return {
        "name": name,
        "aliases": aliases,
        "allergen_tags": tags,
        "plainLanguage": plain,
        "whyForYouTemplate": why,
    }


INGREDIENT_KB = {
    "red40": _entry(
        "Red 40",
        ["red 40", "fd&c red no. 40", "allura red ac", "e129"],
        [],
        "A synthetic dye made from petroleum, used to make foods look redder than the ingredients actually would on their own.",
        "Flagged because it's a synthetic dye — some people react to it even without a formal allergy.",
    ),
    "natural-flavor": _entry(
        "Natural Flavor",
        ["natural flavor", "natural flavoring", "natural flavors"],
        [],
        "A catch-all term for flavor compounds from real plant/animal sources — the exact recipe isn't disclosed.",
        "Flagged as 'unclear' because the exact source can't be confirmed from the label alone.",
    ),
    "milk": _entry(
        "Milk / Dairy",
        ["milk", "dairy", "whey", "casein", "caseinate", "lactose", "ghee", "butter", "cream", "cheese", "yogurt", "milk solids"],
        ["dairy", "milk"],
        "Derived from cow's milk. Includes whey, casein and ghee even when 'milk' isn't listed directly.",
        "Flagged because dairy is on your allergen profile.",
    ),
    "egg": _entry(
        "Egg",
        ["egg", "eggs", "egg white", "egg yolk", "albumin", "albumen", "lysozyme"],
        ["egg"],
        "Whole egg or egg-derived proteins such as albumin.",
        "Flagged because egg is on your allergen profile.",
    ),
    "fish": _entry(
        "Fish",
        ["fish", "salmon", "tuna", "cod", "anchovy", "anchovies", "tilapia", "sardine", "haddock"],
        ["fish"],
        "Finned fish and fish-derived ingredients.",
        "Flagged because fish is on your allergen profile.",
    ),
    "shellfish": _entry(
        "Shellfish",
        ["shellfish", "shrimp", "prawn", "prawns", "crab", "lobster", "crayfish", "clam", "mussel", "oyster", "scallop"],
        ["shellfish"],
        "Crustaceans and molluscs.",
        "Flagged because shellfish is on your allergen profile.",
    ),
    "tree-nut": _entry(
        "Tree Nuts",
        ["almond", "almonds", "cashew", "cashews", "walnut", "walnuts", "pecan", "pecans", "pistachio", "pistachios", "hazelnut", "hazelnuts", "macadamia", "brazil nut", "brazil nuts"],
        ["tree-nut", "tree nut", "tree_nut"],
        "Nuts that grow on trees, such as almonds, cashews and walnuts.",
        "Flagged because tree nuts are on your allergen profile.",
    ),
    "peanut": _entry(
        "Peanut",
        ["peanut", "peanuts", "groundnut", "groundnuts", "arachis oil"],
        ["peanut"],
        "A legume, one of the most common food allergens.",
        "Flagged because peanut is on your allergen profile.",
    ),
    "wheat": _entry(
        "Wheat",
        ["wheat", "semolina", "durum", "spelt", "farina", "wheat gluten"],
        ["wheat"],
        "A cereal grain containing gluten, found in many flours and baked goods.",
        "Flagged because wheat is on your allergen profile.",
    ),
    "soy": _entry(
        "Soy",
        ["soy", "soya", "soybean", "soybeans", "soy lecithin", "tofu", "edamame", "miso", "tempeh"],
        ["soy"],
        "A legume used whole or as protein, oil and lecithin.",
        "Flagged because soy is on your allergen profile.",
    ),
    "sesame": _entry(
        "Sesame",
        ["sesame", "tahini", "sesame oil", "sesame seeds"],
        ["sesame"],
        "Seeds and oil from the sesame plant.",
        "Flagged because sesame is on your allergen profile.",
    ),
}


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
def compute_verdict(ocr_text: str, profile_allergens: List[str]):
    alnum_chars = re.sub(r"[^a-z0-9]", "", ocr_text)
    if len(alnum_chars) < MIN_OCR_ALNUM_CHARS:
        return (
            "unclear",
            [],
            "Couldn't read enough text from this label to check it safely. "
            "Try a clearer, well-lit photo of the ingredients panel.",
        )

    if "ingredient" not in ocr_text:
        return (
            "unclear",
            [],
            "No ingredients list found in this image. Nutrition Facts panels "
            "don't list allergens, so please photograph the ingredients section.",
        )

    flagged = []
    unclear = False

    for ing_id, ing in INGREDIENT_KB.items():
        for alias in ing["aliases"]:
            if re.search(r"\b" + re.escape(alias) + r"\b", ocr_text):
                is_profile_match = any(tag in profile_allergens for tag in ing["allergen_tags"])
                is_ambiguous = len(ing["allergen_tags"]) == 0 and ing_id == "natural-flavor"
                if is_profile_match:
                    flagged.append({"id": ing_id, "name": ing["name"]})
                elif is_ambiguous:
                    unclear = True
                break

    if flagged:
        verdict, note = "flagged", None
    elif unclear:
        verdict, note = "unclear", "Contains an ingredient whose exact source can't be confirmed from the label alone."
    else:
        verdict, note = "safe", None

    return verdict, flagged, note


# ---------------------------------------------------------------
# ROUTES
# ---------------------------------------------------------------

@app.post("/api/scan", response_model=ScanResult)
async def scan_label(file: UploadFile = File(...), product_name: Optional[str] = "Scanned Product"):
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
    verdict, flagged, note = compute_verdict(ocr_text, db.get_profile()["allergens"])

    scan_id = str(uuid.uuid4())[:8]
    scan = {
        "scanId": scan_id,
        "productName": product_name,
        "date": "today",
        "verdict": verdict,
        "flaggedIngredients": flagged,
        "note": note,
    }
    db.save_scan(scan)
    return scan


@app.get("/api/scans", response_model=List[ScanResult])
def list_scans():
    return db.list_scans()  # already most-recent-first


@app.get("/api/scans/{scan_id}", response_model=ScanResult)
def get_scan(scan_id: str):
    scan = db.get_scan(scan_id)
    if not scan:
        raise HTTPException(404, "Scan not found")
    return scan


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
def get_swaps_for_scan(scan_id: str):
    scan = db.get_scan(scan_id)
    if not scan:
        raise HTTPException(404, "Scan not found")
    # Build a craving-signature query vector from the flagged ingredient(s)
    # and product name, then rank via the trained VAE's latent space
    # instead of the old tag-overlap heuristic.
    text_source = " ".join([ing["name"] for ing in scan["flaggedIngredients"]] + [scan["productName"]])
    query_vec = flagged_item_to_vector(text_source)
    return {"query": scan["productName"], "results": rank_swaps_vae(query_vec)}


@app.get("/api/swaps")
def search_swaps(q: str):
    query_vec = craving_text_to_vector(q)
    return {"query": q, "results": rank_swaps_vae(query_vec)}


@app.get("/api/profile")
def get_profile():
    return db.get_profile()


@app.post("/api/profile")
def set_profile(profile: ProfileIn):
    return db.set_profile(profile.allergens)


@app.get("/")
def root():
    return {"status": "ok", "service": "safebite-backend"}


@app.get("/health")
def health():
    return {"status": "ok", "service": "safebite-backend"}