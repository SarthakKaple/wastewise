from tips import generate_tips


def make_result(usage, baseline, flagged=None):
    return {"resources": {"electricity": {
        "usage": usage, "baseline": baseline, "score": 0, "band": "Good",
        "flagged_days": flagged or []}}}


def test_no_issue_gives_positive_message():
    tips = generate_tips(make_result(100, 100))
    assert len(tips) == 1 and "Great job" in tips[0]


def test_high_usage_gives_tip():
    tips = generate_tips(make_result(140, 100))
    assert any("40% above" in t for t in tips)


def test_leak_tip():
    tips = generate_tips(make_result(100, 100), leak_detected=True)
    assert any("leak" in t.lower() for t in tips)


def test_geyser_tip_only_when_listed():
    with_geyser = generate_tips(make_result(150, 100), appliances="geyser")
    without = generate_tips(make_result(150, 100), appliances="")
    assert any("Reduce geyser" in t for t in with_geyser)
    assert not any("Reduce geyser" in t for t in without)


def test_repeated_spikes_tip():
    tips = generate_tips(make_result(100, 100, ["d1", "d2", "d3"]))
    assert any("unusually high days" in t for t in tips)