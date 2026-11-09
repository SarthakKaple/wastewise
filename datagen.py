import numpy as np
import pandas as pd

# Typical daily use per person (rough values used to build fake data)
PER_PERSON = {
    "water": 135,        # litres
    "electricity": 2.2,  # kWh
    "gas": 0.10,         # kg of LPG
}
NOISE = {"water": 0.10, "electricity": 0.10, "gas": 0.12}  # normal day-to-day variation


def generate_usage(days=60, members=4, n_anomalies=6, seed=42):
    """Make fake daily readings for water, electricity and gas.
    Some days get a spike. Returns a DataFrame with the column is_anomaly
    (1 = spike we injected, 0 = normal), which we need later to measure F1."""
    rng = np.random.default_rng(seed)
    dates = pd.date_range("2026-09-01", periods=days)
    rows = []

    for resource, per_person in PER_PERSON.items():
        base = per_person * members
        values = rng.normal(base, base * NOISE[resource], size=days)
        values = np.clip(values, 0, None)

        # pick random days (skip the first 7 so the baseline has history)
        spike_days = rng.choice(np.arange(7, days), size=n_anomalies, replace=False)
        labels = np.zeros(days, dtype=int)
        for d in spike_days:
            values[d] = values[d] * rng.uniform(1.6, 2.5)  # 60% to 150% higher
            labels[d] = 1

        for i in range(days):
            rows.append({
                "date": dates[i].strftime("%Y-%m-%d"),
                "resource": resource,
                "value": round(float(values[i]), 2),
                "is_anomaly": int(labels[i]),
            })

    return pd.DataFrame(rows)


def generate_night_flow(days=30, leak_days=(10, 11, 12, 20, 21), seed=7):
    """Fake hourly water flow for the night hours (1 am to 4 am).
    Normally the flow is 0. On leak days it never reaches 0."""
    rng = np.random.default_rng(seed)
    dates = pd.date_range("2026-09-01", periods=days)
    rows = []
    for i in range(days):
        leak = i in leak_days
        for hour in (1, 2, 3, 4):
            flow = rng.uniform(1.5, 4.0) if leak else 0.0
            rows.append({
                "date": dates[i].strftime("%Y-%m-%d"),
                "hour": hour,
                "flow": round(float(flow), 2),
                "is_leak": int(leak),
            })
    return pd.DataFrame(rows)


def load_into_db(df, household_id):
    """Save a generated DataFrame into the readings table."""
    import db
    for _, r in df.iterrows():
        db.add_reading(household_id, r["date"], r["resource"], r["value"])


if __name__ == "__main__":
    usage = generate_usage()
    print(usage.head(10))
    print("\nTotal rows:", len(usage))
    print("Injected anomalies:", usage["is_anomaly"].sum())
    print("\nAverage per resource:")
    print(usage.groupby("resource")["value"].mean().round(2))

    night = generate_night_flow()
    print("\nLeak nights:", night[night["is_leak"] == 1]["date"].nunique())