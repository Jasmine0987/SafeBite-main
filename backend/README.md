# SafeBite Backend — Core Scan Flow

## Setup
```bash
pip install -r requirements.txt
# macOS: brew install tesseract   |   Ubuntu: apt install tesseract-ocr
uvicorn main:app --reload --host 0.0.0.0 --port 8000
```
Visit `http://localhost:8000/docs` for interactive API testing.

## What's real vs. mocked right now
| Piece | Status |
|---|---|
| OCR | **Real** — pytesseract, works today |
| Verdict engine | **Real** — rule-based keyword match against profile |
| Panel detection | Stub (uses whole image) — plug in your YOLO model in `detect_panel()` |
| Ingredient explanations | Static KB — plug in your captioner model in `INGREDIENT_KB` |
| BiLSTM nudges | Not built — Person C's swap/history territory |

## Wiring your frontend to this instead of app-data.js
In `app.js`, replace the mock lookups with fetch calls, e.g.:
```js
// instead of getScanById(id):
fetch(`http://localhost:8000/api/scans/${id}`).then(r => r.json())

// instead of scan-capture-btn faking a delay:
const formData = new FormData();
formData.append('file', capturedImageBlob);
fetch('http://localhost:8000/api/scan', { method:'POST', body: formData })
  .then(r => r.json())
  .then(scan => window.location.href = `verdict.html?scanId=${scan.scanId}`);
```
Response shapes match `MOCK_SCANS` / `MOCK_INGREDIENTS` exactly, so verdict.html and ingredient-detail.html need zero changes — only the fetch source changes.