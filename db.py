import sqlite3
import pandas as pd

DB_NAME = "wastewise.db"
DEFAULT_WEIGHTS = {"water": 0.35, "electricity": 0.40, "gas": 0.25}


def get_connection():
    conn = sqlite3.connect(DB_NAME)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS household (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            members INTEGER NOT NULL,
            appliances TEXT
        )
    """)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS readings (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            household_id INTEGER NOT NULL,
            date TEXT NOT NULL,
            resource TEXT NOT NULL,
            value REAL NOT NULL,
            FOREIGN KEY (household_id) REFERENCES household(id)
        )
    """)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS alerts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            household_id INTEGER NOT NULL,
            date TEXT NOT NULL,
            resource TEXT NOT NULL,
            message TEXT NOT NULL,
            FOREIGN KEY (household_id) REFERENCES household(id)
        )
    """)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS settings (
            household_id INTEGER PRIMARY KEY,
            w_water REAL NOT NULL,
            w_electricity REAL NOT NULL,
            w_gas REAL NOT NULL,
            FOREIGN KEY (household_id) REFERENCES household(id)
        )
    """)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS night_checks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            household_id INTEGER NOT NULL,
            date TEXT NOT NULL,
            night_reading REAL NOT NULL,
            morning_reading REAL NOT NULL,
            FOREIGN KEY (household_id) REFERENCES household(id)
        )
    """)
    conn.commit()
    conn.close()


def add_household(name, members, appliances=""):
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO household (name, members, appliances) VALUES (?, ?, ?)",
        (name, members, appliances),
    )
    conn.commit()
    household_id = cur.lastrowid
    conn.close()
    return household_id


def get_household(household_id):
    conn = get_connection()
    row = conn.execute(
        "SELECT * FROM household WHERE id = ?", (household_id,)
    ).fetchone()
    conn.close()
    return dict(row) if row else None


def add_reading(household_id, date, resource, value):
    """Save a reading. If one already exists for the same date and resource, it is replaced."""
    conn = get_connection()
    conn.execute(
        "DELETE FROM readings WHERE household_id = ? AND date = ? AND resource = ?",
        (household_id, date, resource),
    )
    conn.execute(
        "INSERT INTO readings (household_id, date, resource, value) VALUES (?, ?, ?, ?)",
        (household_id, date, resource, value),
    )
    conn.commit()
    conn.close()


def get_readings(household_id):
    conn = get_connection()
    df = pd.read_sql_query(
        "SELECT date, resource, value FROM readings WHERE household_id = ? ORDER BY date",
        conn,
        params=(household_id,),
    )
    conn.close()
    return df


def save_alert(household_id, date, resource, message):
    conn = get_connection()
    conn.execute(
        "INSERT INTO alerts (household_id, date, resource, message) VALUES (?, ?, ?, ?)",
        (household_id, date, resource, message),
    )
    conn.commit()
    conn.close()


def get_alerts(household_id):
    conn = get_connection()
    rows = conn.execute(
        "SELECT date, resource, message FROM alerts WHERE household_id = ? ORDER BY date DESC",
        (household_id,),
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


# ---- new functions for the Flask app ----
def get_all_households():
    conn = get_connection()
    rows = conn.execute("SELECT * FROM household ORDER BY id DESC").fetchall()
    conn.close()
    return [dict(r) for r in rows]


def count_readings(household_id):
    conn = get_connection()
    n = conn.execute(
        "SELECT COUNT(*) FROM readings WHERE household_id = ?", (household_id,)
    ).fetchone()[0]
    conn.close()
    return n


def get_recent_readings(household_id, limit=15):
    conn = get_connection()
    rows = conn.execute(
        "SELECT id, date, resource, value FROM readings WHERE household_id = ? "
        "ORDER BY date DESC, id DESC LIMIT ?",
        (household_id, limit),
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def delete_reading(household_id, reading_id):
    conn = get_connection()
    conn.execute(
        "DELETE FROM readings WHERE id = ? AND household_id = ?",
        (reading_id, household_id),
    )
    conn.commit()
    conn.close()


def add_readings_bulk(rows):
    """rows = list of (household_id, date, resource, value).
    Existing readings for the same household, date and resource are replaced."""
    conn = get_connection()
    conn.executemany(
        "DELETE FROM readings WHERE household_id = ? AND date = ? AND resource = ?",
        [(r[0], r[1], r[2]) for r in rows],
    )
    conn.executemany(
        "INSERT INTO readings (household_id, date, resource, value) VALUES (?, ?, ?, ?)",
        rows,
    )
    conn.commit()
    conn.close()


# ---- weights (adjustable per household) ----
def get_weights(household_id):
    conn = get_connection()
    row = conn.execute(
        "SELECT w_water, w_electricity, w_gas FROM settings WHERE household_id = ?",
        (household_id,),
    ).fetchone()
    conn.close()
    if row is None:
        return dict(DEFAULT_WEIGHTS)
    return {"water": row["w_water"], "electricity": row["w_electricity"], "gas": row["w_gas"]}


def set_weights(household_id, weights):
    conn = get_connection()
    conn.execute(
        "INSERT OR REPLACE INTO settings (household_id, w_water, w_electricity, w_gas) "
        "VALUES (?, ?, ?, ?)",
        (household_id, weights["water"], weights["electricity"], weights["gas"]),
    )
    conn.commit()
    conn.close()


def reset_weights(household_id):
    conn = get_connection()
    conn.execute("DELETE FROM settings WHERE household_id = ?", (household_id,))
    conn.commit()
    conn.close()


# ---- overnight water meter checks (leak detection) ----
def add_night_check(household_id, date, night_reading, morning_reading):
    conn = get_connection()
    conn.execute(
        "INSERT INTO night_checks (household_id, date, night_reading, morning_reading) "
        "VALUES (?, ?, ?, ?)",
        (household_id, date, night_reading, morning_reading),
    )
    conn.commit()
    conn.close()


def get_night_checks(household_id, limit=10):
    conn = get_connection()
    rows = conn.execute(
        "SELECT id, date, night_reading, morning_reading FROM night_checks "
        "WHERE household_id = ? ORDER BY date DESC, id DESC LIMIT ?",
        (household_id, limit),
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


if __name__ == "__main__":
    init_db()
    print("Database ready.")
