"""
SafeBite config
================
Small, explicit, and read from env vars so nothing here needs a code
change to go from "dev on my laptop" to "deployed somewhere real."
"""

import os

# ---------------------------------------------------------------------------
# CORS
# ---------------------------------------------------------------------------
# Old code: allow_origins=["*"] — fine while the frontend is a static file
# opened on your own machine, but it means literally any website in a
# user's browser could call this API on their behalf once it's deployed
# somewhere with real user data attached to it.
#
# Default here is a small allowlist covering the common ways people serve
# a static frontend locally (VS Code Live Server, `python -m http.server`,
# a Vite/Node dev server). Override with a comma-separated env var when you
# deploy, e.g.:
#   ALLOWED_ORIGINS=https://safebite.example.com,https://www.safebite.example.com
_default_dev_origins = (
    "http://localhost:5500,http://127.0.0.1:5500,"
    "http://localhost:5173,http://127.0.0.1:5173,"
    "http://localhost:3000,http://127.0.0.1:3000,"
    "http://localhost:8080,http://127.0.0.1:8080"
)

_raw_origins = os.getenv("ALLOWED_ORIGINS", _default_dev_origins)
ALLOWED_ORIGINS = [o.strip() for o in _raw_origins.split(",") if o.strip()]

# ---------------------------------------------------------------------------
# Ollama
# ---------------------------------------------------------------------------
OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "llama3.2")

# ---------------------------------------------------------------------------
# OCR safety threshold
# ---------------------------------------------------------------------------
# Minimum number of alphanumeric characters OCR must extract before we'll
# trust it enough to run the verdict engine over it. Below this, we return
# "unclear" rather than risk a false "safe" on a label we couldn't read.
MIN_OCR_ALNUM_CHARS = 8

# ---------------------------------------------------------------------------
# Tesseract binary path
# ---------------------------------------------------------------------------
# On Windows, pytesseract frequently can't find tesseract.exe even when the
# installer added it to PATH — set TESSERACT_CMD explicitly if OCR keeps
# silently failing. Typical Windows install path is included as a fallback
# guess; it's only used if that exact file exists, so this is a no-op on
# Mac/Linux where the binary is just called "tesseract" on PATH.
TESSERACT_CMD = os.getenv("TESSERACT_CMD")
if not TESSERACT_CMD:
    _default_windows_path = r"C:\Program Files\Tesseract-OCR\tesseract.exe"
    if os.path.exists(_default_windows_path):
        TESSERACT_CMD = _default_windows_path