import pandas as pd
import pytest

import db
from analysis import overnight_leak, weekly_score_history


@pytest.fixture
def temp_db(tmp_path, monkeypatch):
    monkeypatch.setattr(db, "DB_NAME", str(tmp_path / "test.db"))
    db.init_db()
    return db


# ---------- analysis ----------
def test_overnight_leak_detected():
    leak, used = overnight_leak(1000, 1015)
    assert leak is True and used == 15


def test_overnight_no_leak_within_tolerance():
    leak, used = overnight_leak(1000, 1001)
    assert leak is False and used == 1


def make_usage(days_normal, days_high):
    dates = pd.date_range("2026-10-01", periods=days_normal + days_high)
    values = [100.0] * days_normal + [200.0] * days_high
    return pd.DataFrame({"date": dates.strftime("%Y-%m-%d"),
                         "resource": "water", "value": values})


def test_weekly_history_rises_when_usage_rises():
    history = weekly_score_history(make_usage(14, 7), members=4)
    assert len(history) == 3
    assert history[1]["overall"] == 0          # normal week, same as baseline
    assert history[2]["overall"] == 100        # usage doubled -> 100% excess


def test_weekly_history_last_label_is_last_data_day():
    history = weekly_score_history(make_usage(17, 0), members=4)
    assert history[-1]["week_end"] == "2026-10-17"   # partial last week, not Oct 21


def test_weekly_history_empty_data():
    empty = pd.DataFrame({"date": [], "resource": [], "value": []})
    assert weekly_score_history(empty, members=4) == []


def test_weekly_history_uses_weights():
    df = pd.concat([make_usage(14, 7),
                    make_usage(14, 0).assign(resource="gas")])
    # gas stays at 100 (benchmark for 1 member is 0.1, so its own score is capped at 100)
    h1 = weekly_score_history(df, members=4, weights={"water": 1, "electricity": 0, "gas": 0})
    assert h1[-1]["overall"] == h1[-1]["scores"]["water"]


# ---------- database ----------
def test_default_and_custom_weights(temp_db):
    hid = db.add_household("Test", 3)
    assert db.get_weights(hid) == db.DEFAULT_WEIGHTS
    db.set_weights(hid, {"water": 0.5, "electricity": 0.3, "gas": 0.2})
    assert db.get_weights(hid)["water"] == 0.5
    db.reset_weights(hid)
    assert db.get_weights(hid) == db.DEFAULT_WEIGHTS


def test_same_date_reading_is_replaced(temp_db):
    hid = db.add_household("Test", 3)
    db.add_reading(hid, "2026-11-01", "water", 400)
    db.add_reading(hid, "2026-11-01", "water", 500)
    assert db.count_readings(hid) == 1
    assert db.get_readings(hid).iloc[0]["value"] == 500


def test_bulk_insert_replaces_existing(temp_db):
    hid = db.add_household("Test", 3)
    db.add_reading(hid, "2026-11-01", "water", 400)
    db.add_readings_bulk([(hid, "2026-11-01", "water", 450), (hid, "2026-11-02", "water", 460)])
    assert db.count_readings(hid) == 2


def test_delete_reading(temp_db):
    hid = db.add_household("Test", 3)
    db.add_reading(hid, "2026-11-01", "water", 400)
    reading = db.get_recent_readings(hid)[0]
    db.delete_reading(hid, reading["id"])
    assert db.count_readings(hid) == 0


def test_delete_only_own_household(temp_db):
    a = db.add_household("A", 3)
    b = db.add_household("B", 3)
    db.add_reading(a, "2026-11-01", "water", 400)
    rid = db.get_recent_readings(a)[0]["id"]
    db.delete_reading(b, rid)               # wrong household -> nothing deleted
    assert db.count_readings(a) == 1


def test_night_checks_saved(temp_db):
    hid = db.add_household("Test", 3)
    db.add_night_check(hid, "2026-11-02", 1000, 1010)
    checks = db.get_night_checks(hid)
    assert len(checks) == 1 and checks[0]["morning_reading"] == 1010
