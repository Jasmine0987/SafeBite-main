from pathlib import Path

from eval import evaluate as ev

SAMPLE = Path(__file__).resolve().parents[2] / "eval" / "sample_cases.csv"


def test_wilson_interval_bounds():
    lo, hi = ev.wilson(0, 20)
    assert lo == 0.0 and 0.1 < hi < 0.2
    assert ev.wilson(0, 0) is None


def test_cer_wer_identical_and_different():
    assert ev.cer_wer("milk, soy", "milk, soy") == (0.0, 0.0)
    cer, wer = ev.cer_wer("milk soy", "mlk soy")
    assert 0 < cer < 0.3 and wer == 0.5


def test_sample_set_has_no_false_negative():
    m = ev.evaluate(ev.load(str(SAMPLE)), ev.full_verdict)
    assert m["counts"]["fn"] == 0, m["errors"]
    assert m["counts"]["trace_miss"] == 0


def test_context_logic_reduces_false_alarms_vs_baseline():
    rows = ev.load(str(SAMPLE))
    full, base = ev.evaluate(rows, ev.full_verdict), ev.evaluate(rows, ev.baseline_verdict)
    assert full["counts"]["fp"] < base["counts"]["fp"]


def test_blank_rows_are_skipped():
    rows = [{"id": "x", "text": "", "profile": "milk", "truth": "milk", "trace": ""}]
    assert ev.evaluate(rows, ev.full_verdict)["labels"] == 0
