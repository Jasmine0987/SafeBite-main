# Evaluation

`python -m eval.evaluate <file.csv>` from `backend/` prints recall, **false-negative rate** (with 95% Wilson interval), fail-safe rate, precision, false-alarm rate, unclear rate and "may contain" miss rate. It scores the plain-keyword baseline on the same rows. See the docstring in `evaluate.py` for the column format.

* `sample_cases.csv` is 30 hand-written rows to show the format and to guard against regressions. They are NOT real labels, so the numbers they produce are not an accuracy claim.
* For the paper or beta: photograph 200-500 real packs (varied lighting, angles, brands), type the ingredients into `text`, fill `profile`/`truth`/`trace`, put the photo path in `image`. Run once with `--source text` (is the logic right?) and once with `--source ocr` (end to end). With images and `text` present, OCR character/word error rate is printed as well.
* `python -m eval.export_feedback eval/feedback_cases.csv` turns "Report a problem" submissions into rows to annotate.
* `python -m eval.export_alias_audit eval/alias_audit.csv` lists every alias and exclusion for a person to tick Y/N.
