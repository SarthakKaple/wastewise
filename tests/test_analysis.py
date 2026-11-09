import pandas as pd
from analysis import (validate, compute_baseline, detect_zscore, detect_iqr,
                      detect_baseline, leak_check, waste_score, overall_score,
                      score_band, precision_recall_f1)


def test_waste_score_basic():
    assert waste_score(150, 100) == 50


def test_waste_score_no_waste_is_zero():
    assert waste_score(80, 100) == 0


def test_waste_score_capped_at_100():
    assert waste_score(500, 100) == 100


def test_waste_score_zero_baseline():
    assert waste_score(50, 0) == 0


def test_score_bands():
    assert score_band(10) == "Good"
    assert score_band(25) == "Good"
    assert score_band(26) == "Moderate"
    assert score_band(60) == "High"
    assert score_band(90) == "Severe"


def test_overall_score_weighted():
    scores = {"water": 100, "electricity": 0, "gas": 0}
    assert round(overall_score(scores), 2) == 35.0


def test_overall_score_missing_resource():
    # only water given -> weights are renormalised, so the result is its own score
    assert overall_score({"water": 40}) == 40


def test_validate_removes_bad_rows():
    df = pd.DataFrame({
        "date": ["2026-11-01", "2026-11-01", "2026-11-02", "2026-11-03"],
        "resource": ["water", "water", "water", "water"],
        "value": [100, 120, -5, None],
    })
    clean = validate(df)
    assert len(clean) == 1                 # duplicate, negative and missing removed
    assert clean.iloc[0]["value"] == 120   # last duplicate is kept


def test_baseline_uses_benchmark_when_no_history():
    s = pd.Series([100, 110, 105], index=pd.date_range("2026-11-01", periods=3))
    b = compute_baseline(s, members=4, resource="water")
    assert (b == 135 * 4).all()


def test_baseline_uses_rolling_median_with_history():
    s = pd.Series([100.0] * 20, index=pd.date_range("2026-11-01", periods=20))
    b = compute_baseline(s, members=4, resource="water")
    assert b.iloc[-1] == 100


def test_iqr_flags_spike():
    s = pd.Series([10, 11, 9, 10, 12, 10, 11, 9, 10, 50])
    flags = detect_iqr(s)
    assert flags.iloc[-1] and flags.sum() == 1


def test_zscore_flags_spike():
    s = pd.Series([10] * 20 + [100])
    flags = detect_zscore(s)
    assert flags.iloc[-1] and flags.sum() == 1


def test_zscore_constant_series_no_flags():
    assert detect_zscore(pd.Series([5, 5, 5, 5])).sum() == 0


def test_baseline_detector():
    s = pd.Series([100, 100, 140])
    b = pd.Series([100, 100, 100])
    assert list(detect_baseline(s, b)) == [False, False, True]


def test_leak_check():
    night = pd.DataFrame({
        "date": ["d1"] * 4 + ["d2"] * 4,
        "hour": [1, 2, 3, 4] * 2,
        "flow": [0, 0, 0, 0, 2.0, 1.5, 3.0, 2.2],
    })
    result = leak_check(night)
    assert not result["d1"]
    assert result["d2"]


def test_precision_recall_f1():
    p, r, f = precision_recall_f1([1, 1, 0, 0], [1, 0, 1, 0])
    assert (p, r, f) == (0.5, 0.5, 0.5)