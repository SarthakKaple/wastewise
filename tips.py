RESOURCE_TIPS = {
    "water": "Fix dripping taps, take shorter showers and run washing machines only with full loads.",
    "electricity": "Switch off devices on standby, use the geyser and AC only when needed, and prefer LED lights.",
    "gas": "Cover pots while cooking, keep burners clean, and use a pressure cooker to save LPG.",
}


def generate_tips(result, leak_detected=False, appliances=""):
    """Turn the analysis result into a list of saving tips (simple if/else rules).
    result = output of analysis.analyze_household()"""
    tips = []
    appliances = (appliances or "").lower()

    # Rule 1: possible water leak
    if leak_detected:
        tips.append("Night-time water flow detected: check taps, pipes and the toilet tank for leaks.")

    for resource, info in result["resources"].items():
        baseline = info["baseline"]
        if baseline <= 0:
            continue
        pct = (info["usage"] - baseline) / baseline * 100

        # Rule 2: usage above the baseline
        if pct >= 15:
            tips.append(f"{resource.capitalize()} usage is {pct:.0f}% above your normal level. "
                        f"{RESOURCE_TIPS[resource]}")

        # Rule 3: repeated spikes
        if len(info["flagged_days"]) >= 3:
            tips.append(f"{resource.capitalize()} had {len(info['flagged_days'])} unusually high days "
                        f"(latest: {info['flagged_days'][-1]}). Check what happened on those days.")

        # Rule 4: appliance-specific advice
        if resource == "electricity" and pct >= 15:
            if "geyser" in appliances:
                tips.append("Reduce geyser time or lower its temperature setting; it is a major electricity user.")
            if "ac" in appliances.split(",") or "ac" in appliances.split():
                tips.append("Set the AC to 24-26 C and keep doors and windows closed while it runs.")

    # Rule 5: everything is fine
    if not tips:
        tips.append("Great job! Your usage is in line with your normal level. Keep it up.")
    return tips


if __name__ == "__main__":
    from datagen import generate_usage
    from analysis import analyze_household

    # make a case with high usage in the last 7 days
    df = generate_usage()
    mask = (df["date"] >= "2026-10-24") & (df["resource"].isin(["electricity", "water"]))
    df.loc[mask, "value"] = df.loc[mask, "value"] * 1.6

    result = analyze_household(df, members=4)
    print("Overall:", result["overall_score"], result["overall_band"])
    for t in generate_tips(result, leak_detected=True, appliances="geyser, AC"):
        print("-", t)

    print("\nNormal case:")
    result = analyze_household(generate_usage(), members=4)
    for t in generate_tips(result):
        print("-", t)