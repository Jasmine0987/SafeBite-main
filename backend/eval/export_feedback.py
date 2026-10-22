"""
Turn user "Report a problem" submissions into rows for the evaluation set.

    python -m eval.export_feedback eval/feedback_cases.csv

You then open each photo, type the ingredients into `text`, and fill in
`profile` / `truth` / `trace`. Rows left blank are skipped by evaluate.py.
"""
import csv
import sys

from app.core import database as db


def main(path: str) -> None:
    conn = db._get_connection()
    try:
        rows = conn.execute("""
            SELECT f.scan_id, f.kind, f.comment, f.created_at, s.product_name, s.verdict, s.note
            FROM verdict_feedback f LEFT JOIN scans s ON s.scan_id = f.scan_id
            ORDER BY f.created_at""").fetchall()
    finally:
        conn.close()
    with open(path, "w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(["id", "text", "image", "profile", "truth", "trace",
                    "feedback_kind", "comment", "product", "app_verdict", "app_note", "reported_at"])
        for r in rows:
            w.writerow([r["scan_id"], "", "", "", "", "", r["kind"], r["comment"],
                        r["product_name"], r["verdict"], r["note"], r["created_at"]])
    print(f"wrote {len(rows)} rows to {path}")


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "eval/feedback_cases.csv")
