import numpy as np
import pandas as pd

# Reference usage per person per day (used when a household has little history)
BENCHMARK = {"water": 135, "electricity": 2.2, "gas": 0.10}
# Default weights for the overall Waste Score
WEIGHTS = {"water": 0.35, "electricity": 0.40, "gas": 0.25}


# ---------- 1. Cleaning ----------
def validate(df):
    """Remove bad rows: missing values, negatives, duplicates."""
    df = df.copy()
    df["date"] = pd.to_datetime(df["date"], errors="coerce")
    df["value"] = pd.to_numeric(df["value"], errors="coerce")
    df = df.dropna(subset=["date", "resource", "value"])
    df = df[df["value"] >= 0]
    df = df.drop_duplicates(subset=["date", "resource"], keep="last")
    return df.sort_values(["resource", "date"]).reset_index(drop=True)


def get_series(df, resource):
    """Daily series for one resource. Small gaps (up to 2 days) are filled."""
    s = df[df["resource"] == resource].set_index("date")["value"].sort_index()
    if s.empty:
        return s
    full_range = pd.date_range(s.index.min(), s.index.max())
    return s.reindex(full_range).interpolate(limit=2)


# ---------- 2. Baseline ----------
def compute_baseline(series, members, resource, window=14, min_periods=7):
    """Rolling median of the PREVIOUS days. If there is not enough history,
    use the per-person benchmark x number of members."""
    history = series.shift(1).rolling(window, min_periods=min_periods).median()
    fallback = BENCHMARK[resource] * members
    return history.fillna(fallback)


# ---------- 3. Anomaly detection ----------
def detect_zscore(series, threshold=2):
    """Flag days above mean + threshold x standard deviation."""
    std = series.std()
    if np.isnan(std) or std == 0:
        return pd.Series(False, index=series.index)
    z = (series - series.mean()) / std
    return z > threshold


def detect_iqr(series, k=1.5):
    """Flag days above Q3 + k x IQR."""
    q1, q3 = series.quantile(0.25), series.quantile(0.75)
    return series > q3 + k * (q3 - q1)


def detect_baseline(series, baseline, margin=0.3):
    """Flag days where usage exceeds the baseline by more than `margin` (30%)."""
    return series > baseline * (1 + margin)


def leak_check(night_df):
    """A date is a possible leak if flow never drops to zero during night hours.
    night_df needs the columns: date, hour, flow."""
    return night_df.groupby("date")["flow"].min() > 0


# ---------- 4. Waste Score ----------
def waste_score(usage, baseline):
    """E = (U - B) / B x 100, kept between 0 and 100."""
    if baseline <= 0:
        return 0.0
    return float(min(100, max(0, (usage - baseline) / baseline * 100)))


def overall_score(scores, weights=None):
    """Weighted average of the resource scores."""
    weights = weights or WEIGHTS
    used = {r: weights[r] for r in scores if r in weights}
    total = sum(used.values())
    if total == 0:
        return 0.0
    return sum(scores[r] * w for r, w in used.items()) / total


def score_band(score):
    if score <= 25:
        return "Good"
    if score <= 50:
        return "Moderate"
    if score <= 75:
        return "High"
    return "Severe"


def analyze_household(df, members, weights=None, recent_days=7):
    """Full analysis: score for each resource, overall score, flagged days.
    U = average of the last 7 days, B = median of the earlier days
    (or the per-person benchmark if there is not enough history)."""
    df = validate(df)
    result = {"resources": {}}
    scores = {}
    for resource in BENCHMARK:
        s = get_series(df, resource).dropna()
        if s.empty:
            continue
        recent = s.tail(recent_days)
        earlier = s.iloc[:-recent_days]
        usage = recent.mean()
        if len(earlier) >= 7:
            baseline = earlier.median()
        else:
            baseline = BENCHMARK[resource] * members
        score = waste_score(usage, baseline)
        scores[resource] = score
        flagged = s[detect_iqr(s)].index.strftime("%Y-%m-%d").tolist()
        result["resources"][resource] = {
            "usage": round(float(usage), 2),
            "baseline": round(float(baseline), 2),
            "score": round(score, 1),
            "band": score_band(score),
            "flagged_days": flagged,
        }
    overall = overall_score(scores, weights)
    result["overall_score"] = round(overall, 1)
    result["overall_band"] = score_band(overall)
    return result


def overnight_leak(night_reading, morning_reading, tolerance=2.0):
    """Manual version of the night-flow rule. The user notes the water meter just
    before bed and again first thing in the morning. If nobody used water but the
    meter moved by more than `tolerance` litres, the flow never dropped to zero,
    so a leak is possible. Returns (leak_flag, litres_used)."""
    used = morning_reading - night_reading
    return bool(used > tolerance), round(float(used), 2)


def weekly_score_history(df, members, weights=None, block_days=7, min_days=3):
    """Waste Score for each 7-day block, so we can show whether waste is improving.
    For each block: U = block average, B = median of all earlier days
    (or the per-person benchmark if there are fewer than 7 earlier days)."""
    df = validate(df)
    series = {}
    for resource in BENCHMARK:
        s = get_series(df, resource).dropna()
        if not s.empty:
            series[resource] = s
    if not series:
        return []

    start = min(s.index.min() for s in series.values())
    end = max(s.index.max() for s in series.values())
    history = []
    k = 0
    while True:
        block_start = start + pd.Timedelta(days=block_days * k)
        if block_start > end:
            break
        block_end = block_start + pd.Timedelta(days=block_days)
        scores = {}
        block_last = None
        for resource, s in series.items():
            block = s[(s.index >= block_start) & (s.index < block_end)]
            if len(block) < min_days:
                continue
            if block_last is None or block.index.max() > block_last:
                block_last = block.index.max()
            earlier = s[s.index < block_start]
            if len(earlier) >= 7:
                baseline = earlier.median()
            else:
                baseline = BENCHMARK[resource] * members
            scores[resource] = waste_score(block.mean(), baseline)
        if scores:
            history.append({
                "week_end": block_last.strftime("%Y-%m-%d"),
                "scores": {r: round(v, 1) for r, v in scores.items()},
                "overall": round(overall_score(scores, weights), 1),
            })
        k += 1
    return history


# ---------- 5. Evaluation helper ----------
def precision_recall_f1(y_true, y_pred):
    y_true = np.asarray(y_true).astype(bool)
    y_pred = np.asarray(y_pred).astype(bool)
    tp = int((y_true & y_pred).sum())
    fp = int((~y_true & y_pred).sum())
    fn = int((y_true & ~y_pred).sum())
    precision = tp / (tp + fp) if (tp + fp) else 0.0
    recall = tp / (tp + fn) if (tp + fn) else 0.0
    f1 = 2 * precision * recall / (precision + recall) if (precision + recall) else 0.0
    return round(precision, 2), round(recall, 2), round(f1, 2)


if __name__ == "__main__":
    from datagen import generate_usage, generate_night_flow

    raw = generate_usage()
    data = validate(raw)
    members = 4

    # Compare the three detection methods on the fake data
    truth = {"zscore": [], "iqr": [], "baseline": []}
    preds = {"zscore": [], "iqr": [], "baseline": []}
    for resource in BENCHMARK:
        labels = data[data["resource"] == resource]["is_anomaly"].values
        s = get_series(data, resource)
        b = compute_baseline(s, members, resource)
        found = {
            "zscore": detect_zscore(s),
            "iqr": detect_iqr(s),
            "baseline": detect_baseline(s, b),
        }
        for m in found:
            truth[m].extend(labels)
            preds[m].extend(found[m].values)

    print("Detection results (precision, recall, F1):")
    for m in preds:
        print(f"  {m:9s}", precision_recall_f1(truth[m], preds[m]))

    print("\nHousehold analysis:")
    result = analyze_household(raw, members)
    for r, info in result["resources"].items():
        print(f"  {r}: {info['score']} ({info['band']}), usage={info['usage']}, baseline={info['baseline']}")
    print("  Overall:", result["overall_score"], result["overall_band"])

    night = generate_night_flow()
    leaks = leak_check(night)
    print("\nLeak nights found:", int(leaks.sum()))
