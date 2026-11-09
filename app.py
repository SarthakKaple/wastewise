from datetime import datetime

import pandas as pd
from flask import Flask, abort, flash, redirect, render_template, request, url_for

import analysis
import db
from datagen import generate_usage
from tips import generate_tips

app = Flask(__name__)
app.secret_key = "wastewise-dev-key"

RESOURCES = {
    "water": "Water (litres)",
    "electricity": "Electricity (kWh)",
    "gas": "Gas (kg)",
}

db.init_db()


def get_household_or_404(household_id):
    household = db.get_household(household_id)
    if household is None:
        abort(404)
    return household


def is_valid_date(text):
    try:
        datetime.strptime(text, "%Y-%m-%d")
        return True
    except ValueError:
        return False


# ---------------------------------------------------------------- home
@app.route("/")
def index():
    return render_template("index.html", households=db.get_all_households())


@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        name = request.form.get("name", "").strip()
        appliances = request.form.get("appliances", "").strip()
        try:
            members = int(request.form.get("members", ""))
        except ValueError:
            members = 0
        if not name:
            flash("Please enter a household name.", "error")
        elif members < 1 or members > 30:
            flash("Number of members must be between 1 and 30.", "error")
        else:
            household_id = db.add_household(name, members, appliances)
            flash("Household registered. Now add some readings.", "success")
            return redirect(url_for("household", household_id=household_id))
    return render_template("register.html")


@app.route("/household/<int:household_id>")
def household(household_id):
    h = get_household_or_404(household_id)
    return render_template(
        "household.html",
        h=h,
        count=db.count_readings(household_id),
        recent=db.get_recent_readings(household_id),
        resources=RESOURCES,
    )


# ------------------------------------------------------------ readings
@app.route("/household/<int:household_id>/add", methods=["GET", "POST"])
def add_reading(household_id):
    h = get_household_or_404(household_id)
    if request.method == "POST":
        date = request.form.get("date", "")
        resource = request.form.get("resource", "")
        try:
            value = float(request.form.get("value", ""))
        except ValueError:
            value = -1

        if not is_valid_date(date):
            flash("Please choose a valid date.", "error")
        elif resource not in RESOURCES:
            flash("Please choose a resource.", "error")
        elif value < 0:
            flash("Value must be a number that is 0 or more.", "error")
        else:
            db.add_reading(household_id, date, resource, value)
            flash(f"Saved {resource} reading for {date}.", "success")
            return redirect(url_for("add_reading", household_id=household_id))
    today = datetime.now().strftime("%Y-%m-%d")
    return render_template("add.html", h=h, resources=RESOURCES, today=today)


@app.route("/household/<int:household_id>/delete/<int:reading_id>", methods=["POST"])
def delete_reading(household_id, reading_id):
    get_household_or_404(household_id)
    db.delete_reading(household_id, reading_id)
    flash("Reading deleted.", "success")
    return redirect(url_for("household", household_id=household_id))


@app.route("/household/<int:household_id>/upload", methods=["GET", "POST"])
def upload(household_id):
    h = get_household_or_404(household_id)
    if request.method == "POST":
        file = request.files.get("file")
        if not file or file.filename == "":
            flash("Please choose a CSV file.", "error")
            return render_template("upload.html", h=h)
        try:
            raw = pd.read_csv(file)
        except Exception:
            flash("Could not read that file. Make sure it is a valid CSV.", "error")
            return render_template("upload.html", h=h)

        raw.columns = [str(c).strip().lower() for c in raw.columns]
        if not {"date", "resource", "value"}.issubset(raw.columns):
            flash("CSV must have the columns: date, resource, value.", "error")
            return render_template("upload.html", h=h)

        raw = raw[["date", "resource", "value"]].copy()
        raw["resource"] = raw["resource"].astype(str).str.strip().str.lower()
        clean = analysis.validate(raw)
        clean = clean[clean["resource"].isin(RESOURCES)]

        rows = [
            (household_id, d.strftime("%Y-%m-%d"), r, float(v))
            for d, r, v in zip(clean["date"], clean["resource"], clean["value"])
        ]
        if rows:
            db.add_readings_bulk(rows)
        skipped = len(raw) - len(rows)
        flash(f"Uploaded {len(rows)} readings. Skipped {skipped} invalid rows.", "success")
        return redirect(url_for("household", household_id=household_id))
    return render_template("upload.html", h=h)


@app.route("/household/<int:household_id>/sample", methods=["POST"])
def sample(household_id):
    h = get_household_or_404(household_id)
    if db.count_readings(household_id) > 0:
        flash("Sample data can only be added to a household with no readings.", "error")
    else:
        df = generate_usage(members=h["members"])
        rows = [
            (household_id, r["date"], r["resource"], float(r["value"]))
            for _, r in df.iterrows()
        ]
        db.add_readings_bulk(rows)
        flash(f"Added {len(rows)} sample readings.", "success")
    return redirect(url_for("household", household_id=household_id))


# ------------------------------------------------ settings (weights)
@app.route("/household/<int:household_id>/settings", methods=["GET", "POST"])
def settings(household_id):
    h = get_household_or_404(household_id)
    if request.method == "POST":
        if request.form.get("reset"):
            db.reset_weights(household_id)
            flash("Weights reset to the defaults.", "success")
            return redirect(url_for("settings", household_id=household_id))
        try:
            raw = {r: float(request.form.get(r, "")) for r in RESOURCES}
        except ValueError:
            raw = None
        if raw is None or any(v < 0 for v in raw.values()):
            flash("Enter each weight as a number that is 0 or more.", "error")
        elif sum(raw.values()) == 0:
            flash("At least one weight must be greater than 0.", "error")
        else:
            total = sum(raw.values())
            db.set_weights(household_id, {r: v / total for r, v in raw.items()})
            flash("Weights saved. The dashboard now uses them.", "success")
            return redirect(url_for("settings", household_id=household_id))
    weights = db.get_weights(household_id)
    pct = {r: round(w * 100) for r, w in weights.items()}
    return render_template("settings.html", h=h, resources=RESOURCES, pct=pct)


# ------------------------------------------- night leak check (water)
def night_check_rows(household_id):
    rows = []
    for c in db.get_night_checks(household_id):
        leak, used = analysis.overnight_leak(c["night_reading"], c["morning_reading"])
        rows.append({**c, "used": used, "leak": leak})
    return rows


@app.route("/household/<int:household_id>/night", methods=["GET", "POST"])
def night_check(household_id):
    h = get_household_or_404(household_id)
    if request.method == "POST":
        date = request.form.get("date", "")
        try:
            night = float(request.form.get("night", ""))
            morning = float(request.form.get("morning", ""))
        except ValueError:
            night = morning = None

        if not is_valid_date(date):
            flash("Please choose a valid date.", "error")
        elif night is None or night < 0 or morning < 0:
            flash("Enter both meter readings as numbers (0 or more).", "error")
        elif morning < night:
            flash("The morning reading cannot be lower than the night reading.", "error")
        else:
            db.add_night_check(household_id, date, night, morning)
            leak, used = analysis.overnight_leak(night, morning)
            if leak:
                flash(f"Possible leak: the meter moved {used} L overnight while no water was in use.", "error")
            else:
                flash("No leak sign: the meter barely moved overnight.", "success")
            return redirect(url_for("night_check", household_id=household_id))
    today = datetime.now().strftime("%Y-%m-%d")
    return render_template("night.html", h=h, checks=night_check_rows(household_id), today=today)


# ----------------------------------------------------------- dashboard
def build_dashboard_data(readings, members):
    """Prepare chart data and the alert list from the stored readings."""
    data = analysis.validate(readings)
    charts, alerts = {}, []
    for resource in RESOURCES:
        s = analysis.get_series(data, resource).dropna()
        if s.empty:
            continue
        baseline = analysis.compute_baseline(s, members, resource)
        flagged = analysis.detect_iqr(s)
        tail = s.tail(90)  # show the last 90 days in the chart
        charts[resource] = {
            "label": RESOURCES[resource],
            "dates": [d.strftime("%Y-%m-%d") for d in tail.index],
            "values": [round(float(v), 2) for v in tail],
            "baseline": [round(float(baseline[d]), 2) for d in tail.index],
            "anomalies": [round(float(s[d]), 2) if flagged[d] else None for d in tail.index],
        }
        for d in s[flagged].index:
            b = float(baseline[d])
            pct = (float(s[d]) - b) / b * 100 if b > 0 else 0
            alerts.append({
                "date": d.strftime("%Y-%m-%d"),
                "resource": resource,
                "value": round(float(s[d]), 2),
                "pct": round(pct),
            })
    alerts.sort(key=lambda a: a["date"], reverse=True)
    return charts, alerts[:10]


@app.route("/household/<int:household_id>/dashboard")
def dashboard(household_id):
    h = get_household_or_404(household_id)
    readings = db.get_readings(household_id)
    if readings.empty:
        flash("Add some readings first to see the dashboard.", "error")
        return redirect(url_for("household", household_id=household_id))

    weights = db.get_weights(household_id)
    result = analysis.analyze_household(readings, h["members"], weights)
    if not result["resources"]:
        flash("No valid readings found. Check your data and try again.", "error")
        return redirect(url_for("household", household_id=household_id))

    charts, alerts = build_dashboard_data(readings, h["members"])
    history = analysis.weekly_score_history(readings, h["members"], weights)
    checks = night_check_rows(household_id)
    leak = any(c["leak"] for c in checks[:3])  # any of the 3 most recent checks
    tips = generate_tips(result, leak_detected=leak, appliances=h["appliances"])
    weights_pct = {r: round(w / sum(weights.values()) * 100) for r, w in weights.items()}
    return render_template(
        "dashboard.html", h=h, result=result, charts=charts, alerts=alerts,
        history=history, checks=checks[:5], leak=leak, tips=tips,
        resources=RESOURCES, weights_pct=weights_pct,
    )


if __name__ == "__main__":
    app.run(debug=True)
