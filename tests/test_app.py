import io

import pytest

import db


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(db, "DB_NAME", str(tmp_path / "test.db"))
    db.init_db()
    import app as app_module
    app_module.app.config["TESTING"] = True
    return app_module.app.test_client()


def register(client, name="Home", members="4", appliances="geyser, AC"):
    return client.post("/register", data={"name": name, "members": members,
                                          "appliances": appliances})


def test_register_valid_and_invalid(client):
    assert register(client).status_code == 302
    bad = register(client, name="", members="0")
    assert bad.status_code == 200 and b"Please enter a household name" in bad.data


def test_unknown_household_is_404(client):
    assert client.get("/household/99").status_code == 404


def test_add_reading_validation(client):
    register(client)
    bad = client.post("/household/1/add",
                      data={"date": "2026-11-01", "resource": "water", "value": "-5"})
    assert b"0 or more" in bad.data
    ok = client.post("/household/1/add",
                     data={"date": "2026-11-01", "resource": "water", "value": "500"})
    assert ok.status_code == 302 and db.count_readings(1) == 1


def test_csv_upload_skips_invalid_rows(client):
    register(client)
    csv = (b"date,resource,value\n2026-11-01,water,520\n2026-11-01,gas,0.4\n"
           b"2026-11-02,water,-50\n2026-11-02,solar,12\nnot-a-date,water,100\n")
    r = client.post("/household/1/upload", data={"file": (io.BytesIO(csv), "t.csv")},
                    content_type="multipart/form-data", follow_redirects=True)
    assert b"Uploaded 2 readings. Skipped 3 invalid rows." in r.data


def test_csv_upload_wrong_columns(client):
    register(client)
    r = client.post("/household/1/upload", data={"file": (io.BytesIO(b"a,b\n1,2\n"), "t.csv")},
                    content_type="multipart/form-data")
    assert b"CSV must have the columns" in r.data


def test_dashboard_needs_readings(client):
    register(client)
    r = client.get("/household/1/dashboard", follow_redirects=True)
    assert b"Add some readings first" in r.data


def test_full_flow_sample_data_to_dashboard(client):
    register(client)
    client.post("/household/1/sample")
    assert db.count_readings(1) == 180
    r = client.get("/household/1/dashboard")
    assert r.status_code == 200
    assert b"Score by resource" in r.data and r.data.count(b"<canvas") == 4  # 3 resources + weekly


def test_weights_change_dashboard(client):
    register(client)
    client.post("/household/1/sample")
    client.post("/household/1/settings", data={"water": "100", "electricity": "0", "gas": "0"})
    assert db.get_weights(1)["water"] == 1.0
    page = client.get("/household/1/dashboard").data
    assert b"water 100%" in page
    client.post("/household/1/settings", data={"reset": "1"})
    assert db.get_weights(1) == db.DEFAULT_WEIGHTS


def test_invalid_weights_rejected(client):
    register(client)
    r = client.post("/household/1/settings", data={"water": "0", "electricity": "0", "gas": "0"})
    assert b"At least one weight" in r.data


def test_night_leak_flows_to_dashboard(client):
    register(client)
    client.post("/household/1/sample")
    r = client.post("/household/1/night", data={"date": "2026-11-02", "night": "1000", "morning": "1012"},
                    follow_redirects=True)
    assert b"Possible leak" in r.data
    page = client.get("/household/1/dashboard").data
    assert b"Possible water leak" in page and b"Night-time water flow detected" in page


def test_night_check_rejects_backwards_meter(client):
    register(client)
    r = client.post("/household/1/night", data={"date": "2026-11-02", "night": "1000", "morning": "990"})
    assert b"cannot be lower" in r.data


def test_delete_reading_route(client):
    register(client)
    client.post("/household/1/add", data={"date": "2026-11-01", "resource": "water", "value": "500"})
    rid = db.get_recent_readings(1)[0]["id"]
    client.post(f"/household/1/delete/{rid}")
    assert db.count_readings(1) == 0
