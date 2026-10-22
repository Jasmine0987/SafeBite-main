"""
SafeBite allergen-verdict evaluation.

Run from backend/:
    python -m eval.evaluate eval/sample_cases.csv
    python -m eval.evaluate my_labels.csv --out eval/results.json
    python -m eval.evaluate my_labels.csv --source ocr      # end to end, from photos

CSV columns (UTF-8, header row required):
    id      any unique label
    text    ground-truth transcription of the ingredients panel (you type it)
    image   optional path to the photo (needed for --source ocr and for CER/WER)
    profile allergens the shopper declared, ";"-separated  e.g. milk;peanut
    truth   allergens genuinely listed as INGREDIENTS on the pack (same names)
    trace   allergens only in a "may contain / made in a facility" statement

Definitions (per label, against that row's profile):
    positive    : truth overlaps profile  (a real allergen is in the food)
    trace-only  : not positive, but trace overlaps profile
    negative    : neither
    false negative (FN): positive label that got "safe"   <- the dangerous error
    fail-safe          : positive label that got "unclear"
    false alarm (FP)   : negative label that got "flagged"
    precaution miss    : trace-only label that got "safe"

The same rows are also scored with context_aware=False (plain keyword match)
so you can report what the "may contain"/"free from" logic adds.
"""
from __future__ import annotations

import argparse
import csv
import json
import math
import re
import sys
from pathlib import Path
from typing import Callable, Dict, List, Optional, Tuple

from app.core import label_analysis as la
from app.core.allergen_kb import INGREDIENT_KB
from app.core.config import MIN_OCR_ALNUM_CHARS

Verdict = Tuple[str, List[dict]]


# ---------------------------------------------------------------------------
# verdict functions under test
# ---------------------------------------------------------------------------
def full_verdict(text: str, profile: List[str]) -> Verdict:
    v, flagged, _ = la.compute_verdict(text, profile, MIN_OCR_ALNUM_CHARS)
    return v, flagged


def baseline_verdict(text: str, profile: List[str]) -> Verdict:
    """Same gates, but plain keyword matching (no precaution / claim / fuzzy logic)."""
    t = la._norm(text)
    if len(re.sub(r"[^a-z0-9]", "", t)) < MIN_OCR_ALNUM_CHARS or not la._has_ingredient_heading(t):
        return "unclear", []
    v, flagged, _ = la._verdict_from_findings(la.analyze(t, profile, context_aware=False)["findings"])
    return v, flagged


# ---------------------------------------------------------------------------
# small helpers
# ---------------------------------------------------------------------------
def split(s: Optional[str]) -> List[str]:
    return [x.strip() for x in (s or "").replace(",", ";").split(";") if x.strip()]


def wilson(k: int, n: int, z: float = 1.96) -> Optional[Tuple[float, float]]:
    """95% Wilson score interval for k successes out of n."""
    if n == 0:
        return None
    p = k / n
    d = 1 + z * z / n
    c = (p + z * z / (2 * n)) / d
    h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return max(0.0, c - h), min(1.0, c + h)


def edit_distance_seq(a, b) -> int:
    prev = list(range(len(b) + 1))
    for i, x in enumerate(a, 1):
        cur = [i]
        for j, y in enumerate(b, 1):
            cur.append(min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (x != y)))
        prev = cur
    return prev[-1]


def _clean(s: str) -> str:
    return re.sub(r"\s+", " ", (s or "").lower()).strip()


def cer_wer(reference: str, hypothesis: str) -> Tuple[float, float]:
    ref, hyp = _clean(reference), _clean(hypothesis)
    cer = edit_distance_seq(ref, hyp) / max(1, len(ref))
    rw, hw = ref.split(), hyp.split()
    wer = edit_distance_seq(rw, hw) / max(1, len(rw))
    return cer, wer


def ocr_image(path: str) -> str:
    """Mirror of run_ocr() in app/main.py (kept separate so this module never imports torch)."""
    import pytesseract
    from PIL import Image, ImageOps
    from app.core.config import TESSERACT_CMD

    if TESSERACT_CMD:
        pytesseract.pytesseract.tesseract_cmd = TESSERACT_CMD
    img = Image.open(path).convert("RGB")
    if img.width < 1500:
        s = 1500 / img.width
        img = img.resize((int(img.width * s), int(img.height * s)), Image.LANCZOS)
    cands = [ImageOps.autocontrast(img.convert("L")), ImageOps.autocontrast(img.split()[1])]
    return max((pytesseract.image_to_string(c, config="--psm 6") for c in cands), key=len).lower()


def load(path: str) -> List[Dict[str, str]]:
    with open(path, newline="", encoding="utf-8-sig") as f:
        return list(csv.DictReader(f))


# ---------------------------------------------------------------------------
# scoring
# ---------------------------------------------------------------------------
def evaluate(rows: List[Dict[str, str]], fn: Callable[[str, List[str]], Verdict],
             texts: Optional[Dict[str, str]] = None) -> dict:
    texts = texts or {}
    c = dict(n=0, pos=0, tp=0, fn=0, failsafe=0, neg=0, fp=0, tn=0, neg_unclear=0,
             trace_only=0, trace_miss=0, unclear_total=0, allergens_true=0, allergens_found=0)
    errors = []
    for row in rows:
        text = texts.get(row.get("id", ""), row.get("text", ""))
        if not text.strip():
            continue
        prof = split(row.get("profile"))
        P = la.expand_profile(prof)
        truth = la.expand_profile(split(row.get("truth")))
        trace = la.expand_profile(split(row.get("trace")))
        verdict, flagged = fn(text, prof)
        covered = set()
        for f in flagged:
            covered |= set(INGREDIENT_KB[f["id"]]["allergen_tags"])

        c["n"] += 1
        c["unclear_total"] += verdict == "unclear"
        if truth & P:
            c["pos"] += 1
            if verdict == "flagged":
                c["tp"] += 1
            elif verdict == "safe":
                c["fn"] += 1
                errors.append((row.get("id"), "FALSE NEGATIVE", text[:80]))
            else:
                c["failsafe"] += 1
            for a in prof:
                A = la.expand_profile([a])
                if A & truth:
                    c["allergens_true"] += 1
                    c["allergens_found"] += bool(covered & A)
        elif trace & P:
            c["trace_only"] += 1
            if verdict == "safe":
                c["trace_miss"] += 1
                errors.append((row.get("id"), "PRECAUTION MISS", text[:80]))
        else:
            c["neg"] += 1
            if verdict == "flagged":
                c["fp"] += 1
                errors.append((row.get("id"), "FALSE ALARM", text[:80]))
            elif verdict == "unclear":
                c["neg_unclear"] += 1
            else:
                c["tn"] += 1
    return summarize(c, errors)


def _rate(k, n):
    return None if n == 0 else k / n


def summarize(c: dict, errors: list) -> dict:
    tp_fp = c["tp"] + c["fp"]
    return {
        "counts": c,
        "labels": c["n"],
        "positives": c["pos"],
        "recall": _rate(c["tp"], c["pos"]),
        "recall_ci95": wilson(c["tp"], c["pos"]),
        "false_negative_rate": _rate(c["fn"], c["pos"]),
        "false_negative_ci95": wilson(c["fn"], c["pos"]),
        "fail_safe_rate_on_positives": _rate(c["failsafe"], c["pos"]),
        "allergen_level_recall": _rate(c["allergens_found"], c["allergens_true"]),
        "precision": _rate(c["tp"], tp_fp),
        "false_alarm_rate": _rate(c["fp"], c["neg"]),
        "unclear_rate": _rate(c["unclear_total"], c["n"]),
        "precaution_miss_rate": _rate(c["trace_miss"], c["trace_only"]),
        "errors": errors,
    }


def _pct(x):
    return "  n/a " if x is None else f"{100 * x:5.1f}%"


def _ci(ci):
    return "" if ci is None else f"  (95% CI {100 * ci[0]:.1f}-{100 * ci[1]:.1f}%)"


def report(name: str, m: dict) -> None:
    print(f"\n=== {name} ===")
    print(f"labels scored            {m['labels']}   (positives: {m['positives']})")
    print(f"allergen recall          {_pct(m['recall'])}{_ci(m['recall_ci95'])}")
    print(f"FALSE-NEGATIVE RATE      {_pct(m['false_negative_rate'])}{_ci(m['false_negative_ci95'])}")
    print(f"fail-safe (unclear) rate {_pct(m['fail_safe_rate_on_positives'])}   on labels that did contain an allergen")
    print(f"allergen-level recall    {_pct(m['allergen_level_recall'])}")
    print(f"precision                {_pct(m['precision'])}")
    print(f"false-alarm rate         {_pct(m['false_alarm_rate'])}")
    print(f"unclear rate (all)       {_pct(m['unclear_rate'])}")
    print(f"precaution-miss rate     {_pct(m['precaution_miss_rate'])}   'may contain' labels answered 'safe'")
    for cid, kind, snip in m["errors"]:
        print(f"  ! {kind:15s} {cid}: {snip}")


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("csv")
    ap.add_argument("--source", choices=["text", "ocr"], default="text",
                    help="text = score the verdict logic on your transcriptions; "
                         "ocr = run Tesseract on each image first (end to end)")
    ap.add_argument("--out", help="write full results to this JSON file")
    args = ap.parse_args(argv)

    rows = load(args.csv)
    skipped = sum(1 for r in rows if not (r.get("text") or "").strip() and not (r.get("image") or "").strip())
    texts: Dict[str, str] = {}
    cers, wers = [], []
    if args.source == "ocr":
        base = Path(args.csv).resolve().parent
        for r in rows:
            img = (r.get("image") or "").strip()
            if not img:
                continue
            p = Path(img) if Path(img).is_absolute() else base / img
            texts[r["id"]] = ocr_image(str(p))
            if (r.get("text") or "").strip():
                cer, wer = cer_wer(r["text"], texts[r["id"]])
                cers.append(cer)
                wers.append(wer)

    full = evaluate(rows, full_verdict, texts)
    base = evaluate(rows, baseline_verdict, texts)
    report(f"SafeBite verdict engine  [{args.source}]", full)
    report("Baseline: plain keyword match", base)
    if cers:
        print(f"\nOCR  mean CER {100 * sum(cers) / len(cers):.1f}%   mean WER {100 * sum(wers) / len(wers):.1f}%   ({len(cers)} images)")
    if skipped:
        print(f"\n(skipped {skipped} rows with no text or image)")
    if full["positives"] < 100:
        print("\nNOTE: fewer than 100 positive labels. The confidence interval is wide; "
              "do not quote these numbers as accuracy.")
    if args.out:
        out = {"source": args.source, "engine": full, "baseline": base,
               "ocr": {"mean_cer": sum(cers) / len(cers), "mean_wer": sum(wers) / len(wers), "n": len(cers)} if cers else None}
        Path(args.out).write_text(json.dumps(out, indent=2, default=list), encoding="utf-8")
        print(f"\nwrote {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
