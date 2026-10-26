"""
Context-aware label analysis.

Replaces the old "any keyword anywhere => flagged" logic with evidence classes:

  definite       allergen appears as an ingredient / "Contains:" statement
  precautionary  appears only inside "may contain / traces of / produced in a
                 facility that handles ..." clauses  -> verdict UNCLEAR (cross-contact risk)
  claim          appears only inside a free-from claim ("dairy free", "no milk")
                 -> ignored (the claim is not an ingredient)
  fuzzy          one OCR typo away from an alias (e.g. "peanuk") -> verdict UNCLEAR

Verdict rules (fail-safe, never silently "safe"):
  any profile allergen definite                  -> flagged
  else precautionary / fuzzy / ambiguous flavour -> unclear (with a specific note)
  else                                           -> safe
Database evidence can only ESCALATE a verdict (safe -> unclear/flagged), never lower it.

Public API (drop-in for main.compute_verdict):
  compute_verdict(ocr_text, profile_allergens, min_chars) -> (verdict, flagged, note)
  compute_verdict_with_database(ocr_text, profile, min_chars, product) -> same tuple
  analyze(text, profile_allergens) -> detailed findings (used by the eval script)
"""
from __future__ import annotations

import re
from typing import Dict, Iterable, List, Optional, Set, Tuple

from app.core.allergen_kb import EXCLUDE_FOR, INGREDIENT_KB

# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------
_SYN = {
    "milk": "dairy", "tree nut": "tree-nut", "tree_nut": "tree-nut", "treenut": "tree-nut",
    "tree nuts": "tree-nut", "tree-nuts": "tree-nut", "peanuts": "peanut", "eggs": "egg",
    "soya": "soy", "soybean": "soy", "crustacean": "shellfish", "crustaceans": "shellfish",
}


def expand_profile(tags: Optional[Iterable[str]]) -> Set[str]:
    """Normalise profile tags so 'tree nut' / 'tree_nut' / 'milk' all match the KB."""
    out: Set[str] = set()
    for t in tags or []:
        k = str(t).strip().lower()
        dashed = k.replace("_", "-").replace(" ", "-")
        for v in (k, dashed, _SYN.get(k, k), _SYN.get(dashed, dashed)):
            out.add(v)
        if k in {"nuts", "nut"}:
            out |= {"tree-nut", "peanut"}
    return out


def edit_distance(a: str, b: str) -> int:
    if a == b:
        return 0
    if not a or not b:
        return max(len(a), len(b))
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        cur = [i]
        for j, cb in enumerate(b, 1):
            cur.append(min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (ca != cb)))
        prev = cur
    return prev[-1]


def _norm(text: str) -> str:
    t = (text or "").lower()
    t = t.replace("\u2010", "-").replace("\u2011", "-").replace("\u2013", "-").replace("\u2014", "-")
    t = re.sub(r"[ \t]+", " ", t)
    return t


# ---------------------------------------------------------------------------
# precautionary clauses and free-from claims
# ---------------------------------------------------------------------------
_PREC_TRIGGER = re.compile(
    r"(?:may|might|could|can)\s+(?:also\s+)?contain"
    r"|contains?\s+traces?\s+of|traces?\s+of"
    r"|(?:produced|processed|manufactured|made|packed|packaged)\s+(?:in|on)\s+"
    r"(?:a|an|the|shared)?[^.;\n]{0,40}?(?:facility|equipment|line|factory|premises|unit|plant|kitchen)"
    r"|(?:shares?|handles?)\s+(?:a\s+)?(?:facility|equipment|line|production)"
    r"|cross[- ]?contact|not\s+suitable\s+for\s+(?:people|those|persons)?[^.;\n]{0,15}allerg"
)
_PREC_MAX = 150  # characters of clause after the trigger


def _precaution_spans(t: str) -> List[Tuple[int, int]]:
    spans = []
    for m in _PREC_TRIGGER.finditer(t):
        start, hard_end = m.start(), min(len(t), m.end() + _PREC_MAX)
        end = hard_end
        # clause ends at sentence punctuation or at the next section heading
        stop = re.search(r"[.;]|ingredient|nutrition|contains\s*:|\bbest before\b", t[m.end():hard_end])
        if stop:
            end = m.end() + stop.start()
        spans.append((start, end))
    return spans


_CLAIM_BEFORE = re.compile(
    r"(?:\bno|\bwithout|free\s+(?:from|of)|contains?\s+no|does\s+not\s+contain|\bnon)[\s-]+(?:added\s+|any\s+)?$")
_CLAIM_AFTER = re.compile(r"^[\s-]*free\b")


def _is_claim(t: str, start: int, end: int) -> bool:
    return bool(_CLAIM_BEFORE.search(t[max(0, start - 18):start])) or bool(_CLAIM_AFTER.match(t[end:end + 10]))


# ---------------------------------------------------------------------------
# compiled alias patterns
# ---------------------------------------------------------------------------
_compiled: Dict[int, Dict[str, dict]] = {}


def _compile(kb: dict) -> Dict[str, dict]:
    key = id(kb)
    if key in _compiled:
        return _compiled[key]
    out = {}
    for ing_id, ing in kb.items():
        aliases = sorted(set(ing["aliases"]), key=len, reverse=True)
        parts = []
        for a in aliases:
            esc = re.escape(a)
            parts.append(esc + (r"(?:s|es)?" if " " not in a and a.isalpha() else ""))
        rx = re.compile(r"\b(?:" + "|".join(parts) + r")\b") if parts else None
        ex = EXCLUDE_FOR.get(ing_id, [])
        ex_rx = re.compile(r"\b(?:" + "|".join(re.escape(e) for e in ex) + r")\b") if ex else None
        singles = [a for a in aliases if " " not in a and a.isalpha() and len(a) >= 6]
        words = [a for a in aliases if " " not in a and a.isalpha() and len(a) >= 3]
        out[ing_id] = {"rx": rx, "ex": ex_rx, "singles": singles, "words": words}
    _compiled[key] = out
    return out


def _fuzzy_hit(t: str, singles: List[str], exact_words: Set[str]) -> Optional[str]:
    if not singles:
        return None
    for tok in set(re.findall(r"[a-z]{6,}", t)):
        if tok in exact_words:
            continue
        for a in singles:
            if abs(len(tok) - len(a)) <= 1 and edit_distance(tok, a) == 1 \
                    and tok.rstrip("s") != a and tok != a + "s":
                return tok
    return None


# OCR often swaps look-alike characters inside SHORT words ("m1lk", "5oy", "eg9",
# "rnilk"). _fuzzy_hit ignores words under 6 letters, so those misreads used to
# fall through as "safe". Only tokens mixing digits and letters (or containing
# rn / vv) are tried, so ordinary words and E-numbers are not touched.
_DIGIT_FIX = {"0": "o", "1": "il", "3": "e", "4": "a", "5": "s", "8": "b", "9": "g"}
_E_NUMBER = re.compile(r"^e\d{3,4}[a-z]?$")


def _confusable_variants(tok: str) -> Set[str]:
    outs = {""}
    for ch in tok:
        opts = _DIGIT_FIX.get(ch, ch)
        outs = {o + c for o in outs for c in opts}
        if len(outs) > 64:
            return set()
    extra = {v.replace("rn", "m").replace("vv", "w") for v in outs} if ("rn" in tok or "vv" in tok) else set()
    return outs | extra


def _ocr_confusable_hit(t: str, words: List[str], exact_words: Set[str]) -> Optional[str]:
    if not words:
        return None
    wanted = set(words)
    for tok in set(re.findall(r"[a-z0-9]{3,12}", t)):
        mixed = any(c.isdigit() for c in tok) and any(c.isalpha() for c in tok)
        if tok in exact_words or _E_NUMBER.match(tok) or not (mixed or "rn" in tok or "vv" in tok):
            continue
        for v in _confusable_variants(tok):
            if v != tok and (v in wanted or (v.endswith("s") and v[:-1] in wanted) or (v.endswith("es") and v[:-2] in wanted)):
                return tok
    return None


# ---------------------------------------------------------------------------
# analysis
# ---------------------------------------------------------------------------
def analyze(text: str, profile_allergens: Optional[Iterable[str]], kb: Optional[dict] = None,
            context_aware: bool = True) -> dict:
    """
    Returns {"findings": [{id,name,status,evidence,profile_match}], ...}.
    context_aware=False reproduces the old keyword baseline (any hit = definite);
    kept so the evaluation script can measure what the context logic adds.
    """
    kb = kb or INGREDIENT_KB
    t = _norm(text)
    compiled = _compile(kb)
    P = expand_profile(profile_allergens)
    prec_spans = _precaution_spans(t) if context_aware else []
    findings = []

    for ing_id, ing in kb.items():
        relevant = bool(set(ing["allergen_tags"]) & P)
        ambiguous = ing_id == "natural-flavor"
        if not (relevant or ambiguous):
            continue
        c = compiled[ing_id]
        statuses, evidence, exact_words = [], None, set()
        if c["rx"]:
            ex_spans = [m.span() for m in c["ex"].finditer(t)] if (c["ex"] and context_aware) else []
            for m in c["rx"].finditer(t):
                s, e = m.span()
                if any(xs <= s and e <= xe for xs, xe in ex_spans):
                    continue
                exact_words.add(m.group(0))
                if context_aware and any(ps <= s < pe for ps, pe in prec_spans):
                    st = "precautionary"
                elif context_aware and _is_claim(t, s, e):
                    st = "claim"
                else:
                    st = "definite"
                statuses.append(st)
                if evidence is None or st == "definite":
                    evidence = m.group(0)
        if "definite" in statuses:
            status = "definite"
        elif "precautionary" in statuses:
            status = "precautionary"
        elif "claim" in statuses:
            status = "claim"
        else:
            status = None
            if context_aware and relevant:
                tok = _fuzzy_hit(t, c["singles"], exact_words) or _ocr_confusable_hit(t, c["words"], exact_words) or _ocr_confusable_hit(t, c["words"], exact_words)
                if tok:
                    status, evidence = "fuzzy", tok
        if status:
            findings.append({"id": ing_id, "name": ing["name"], "status": status,
                             "evidence": evidence, "profile_match": relevant})
    return {"findings": findings}


def _names(items: List[dict]) -> str:
    return ", ".join(sorted({f["name"] for f in items}))


def _verdict_from_findings(findings: List[dict]) -> Tuple[str, List[dict], Optional[str]]:
    rel = [f for f in findings if f["profile_match"]]
    flagged = [{"id": f["id"], "name": f["name"]} for f in rel if f["status"] == "definite"]
    prec = [f for f in rel if f["status"] == "precautionary"]
    fuzzy = [f for f in rel if f["status"] == "fuzzy"]
    ambiguous = [f for f in findings if f["id"] == "natural-flavor" and f["status"] == "definite"]

    notes = []
    if prec:
        notes.append(f"Precautionary label: may contain {_names(prec)}. Not listed as an ingredient, "
                     "but cross-contact is possible. Check the pack against your own risk level.")
    if fuzzy:
        notes.append(f"Possible {_names(fuzzy)} (some text was unclear). Retake the photo to confirm.")
    if flagged:
        return "flagged", flagged, (" ".join(notes) or None)
    if prec or fuzzy:
        return "unclear", [], " ".join(notes)
    if ambiguous:
        return "unclear", [], ("Contains an ingredient whose exact source can't be confirmed "
                               "from the label alone.")
    return "safe", [], None


# ---------------------------------------------------------------------------
# gating (can we trust this OCR read at all?) + public verdict API
# ---------------------------------------------------------------------------
def _has_ingredient_heading(t: str) -> bool:
    for tok in set(re.findall(r"[a-z]{6,}", t)):
        if tok.startswith("ingredient") or tok == "composition":
            return True
        if len(tok) <= 13 and (edit_distance(tok, "ingredients") <= 2 or edit_distance(tok, "ingredient") <= 2):
            return True
    return False


def _verdict(ocr_text: str, profile_allergens, min_chars: int, kb=None):
    t = _norm(ocr_text)
    if len(re.sub(r"[^a-z0-9]", "", t)) < min_chars:
        return ("unclear", [],
                "Couldn't read enough text from this label to check it safely. "
                "Try a clearer, well-lit photo of the ingredients panel.", "unreadable")
    if not _has_ingredient_heading(t):
        return ("unclear", [],
                "No ingredients list found in this image. Nutrition Facts panels "
                "don't list allergens, so please photograph the ingredients section.", "no_ingredients")
    v, flagged, note = _verdict_from_findings(analyze(t, profile_allergens, kb)["findings"])
    return v, flagged, note, "ok"


def compute_verdict(ocr_text: str, profile_allergens, min_chars: int = 8):
    v, flagged, note, _ = _verdict(ocr_text, profile_allergens, min_chars)
    return v, flagged, note


def compute_verdict_with_database(ocr_text: str, profile_allergens, min_chars: int,
                                  product: Optional[dict], kb: Optional[dict] = None):
    """Same as compute_verdict, plus escalation from a product-database record."""
    kb = kb or INGREDIENT_KB
    verdict, flagged, note, reason = _verdict(ocr_text, profile_allergens, min_chars, kb)
    if not product:
        return verdict, flagged, note

    P = expand_profile(profile_allergens)
    relevant = {i for i, ing in kb.items() if set(ing["allergen_tags"]) & P}
    db_def = set(product.get("allergen_ids", [])) & relevant
    db_trace = set(product.get("trace_ids", [])) & relevant
    src = "the product database (Open Food Facts)"
    SRC = src[0].upper() + src[1:]

    if reason != "ok":  # photo unusable: lean on the database, but never claim "safe"
        text_hits = set()
        if product.get("ingredients_text"):
            res = analyze("ingredients: " + product["ingredients_text"], profile_allergens, kb)
            text_hits = {f["id"] for f in res["findings"] if f["profile_match"] and f["status"] == "definite"}
        ids = db_def | text_hits
        if ids:
            names = sorted(kb[i]["name"] for i in ids)
            return ("flagged", [{"id": i, "name": kb[i]["name"]} for i in sorted(ids)],
                    f"Based on {src}, not your photo: contains {', '.join(names)}.")
        return ("unclear", [],
                f"The photo couldn't be read. {SRC} lists none of your allergens, "
                "but databases can be outdated, so verify on the pack.")

    have = {f["id"] for f in flagged}
    new_def = sorted(db_def - have)
    notes = [note] if note else []
    if new_def:
        flagged = flagged + [{"id": i, "name": kb[i]["name"]} for i in new_def]
        notes.append(f"{SRC} lists {', '.join(kb[i]['name'] for i in new_def)}, "
                     "which wasn't clearly visible in your photo. Verify on the pack.")
        verdict = "flagged"
    elif verdict == "safe" and db_trace:
        names = ", ".join(sorted(kb[i]["name"] for i in db_trace))
        notes.append(f"{SRC} lists possible traces of {names}.")
        verdict = "unclear"
    return verdict, flagged, (" ".join(notes) or None)