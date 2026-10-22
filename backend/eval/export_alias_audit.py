"""
Write every alias in allergen_kb.py to a CSV so a person can tick each one.

    python -m eval.export_alias_audit eval/alias_audit.csv

Fill `ok` with Y or N (and `notes`) for each row. Pay most attention to aliases
that map to an allergen but are not obviously one (regional names, E-numbers,
"maida", "groundnut") and to anything in the EXCLUDE rows (false-alarm guards).
"""
import csv
import sys

from app.core import allergen_kb as kb


def main(path: str) -> None:
    n = 0
    with open(path, "w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(["kind", "ingredient_id", "name", "allergen_tags", "alias_or_phrase", "ok", "notes"])
        for ing_id, ing in kb.INGREDIENT_KB.items():
            for alias in ing["aliases"]:
                w.writerow(["alias", ing_id, ing["name"], ";".join(ing["allergen_tags"]), alias, "", ""])
                n += 1
        ex = getattr(kb, "EXCLUDE_FOR", {}) or {}
        for ing_id, phrases in ex.items():
            for p in (phrases if not isinstance(phrases, str) else [phrases]):
                w.writerow(["exclude", ing_id, kb.INGREDIENT_KB.get(ing_id, {}).get("name", ""), "", p, "", ""])
                n += 1
    print(f"wrote {n} rows to {path}")


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "eval/alias_audit.csv")
