#!/usr/bin/env python3
"""
Garmin Connect sync → docs/data.json
Дърпа за последните 7 дни: активности, сън, стъпки, пулс, калории.
"""

import os, json, sys
from datetime import date, timedelta
from pathlib import Path

try:
    from garminconnect import Garmin
except ImportError:
    print("ERROR: garminconnect not installed")
    sys.exit(1)

EMAIL    = os.environ["GARMIN_EMAIL"]
PASSWORD = os.environ["GARMIN_PASSWORD"]
DATA_FILE = Path("docs/data.json")

# ── helpers ──────────────────────────────────────────────────────
def safe(fn, default=None):
    try: return fn()
    except: return default

def load_existing():
    if DATA_FILE.exists():
        try: return json.loads(DATA_FILE.read_text())
        except: pass
    return {}

def save(data):
    DATA_FILE.parent.mkdir(parents=True, exist_ok=True)
    DATA_FILE.write_text(json.dumps(data, ensure_ascii=False, indent=2))

# ── main ─────────────────────────────────────────────────────────
def main():
    print("Connecting to Garmin Connect...")
    api = Garmin(EMAIL, PASSWORD)
    api.login()
    print("Logged in ✓")

    today = date.today()
    data  = load_existing()

    garmin_days = data.get("garmin", {})

    for i in range(7):                         # последните 7 дни
        d = today - timedelta(days=i)
        ds = d.isoformat()

        # ── Activities ──────────────────────────────────────────
        activities = safe(lambda: api.get_activities_by_date(ds, ds), [])
        acts = []
        for a in (activities or []):
            acts.append({
                "type":        a.get("activityType", {}).get("typeKey", "unknown"),
                "name":        a.get("activityName", ""),
                "start":       a.get("startTimeLocal", ""),
                "duration_s":  int(a.get("duration", 0)),
                "distance_m":  round(a.get("distance", 0), 0),
                "calories":    int(a.get("calories", 0)),
                "avg_hr":      safe(lambda: int(a["averageHR"])),
                "max_hr":      safe(lambda: int(a["maxHR"])),
                "avg_speed":   safe(lambda: round(a["averageSpeed"], 2)),
            })

        # ── Steps ───────────────────────────────────────────────
        steps_data = safe(lambda: api.get_steps_data(ds))
        steps = 0
        if steps_data and isinstance(steps_data, list):
            steps = sum(s.get("steps", 0) for s in steps_data)
        elif isinstance(steps_data, dict):
            steps = steps_data.get("totalSteps", 0)

        # ── Heart Rate ──────────────────────────────────────────
        hr_data  = safe(lambda: api.get_heart_rates(ds), {})
        resting_hr = safe(lambda: hr_data.get("restingHeartRate"))

        # ── Sleep ───────────────────────────────────────────────
        sleep_data = safe(lambda: api.get_sleep_data(ds), {})
        sleep = {}
        if sleep_data:
            sd = sleep_data.get("dailySleepDTO", sleep_data)
            total_s = sd.get("sleepTimeSeconds", 0) or 0
            sleep = {
                "total_min":  round(total_s / 60),
                "deep_min":   round((sd.get("deepSleepSeconds",  0) or 0) / 60),
                "light_min":  round((sd.get("lightSleepSeconds", 0) or 0) / 60),
                "rem_min":    round((sd.get("remSleepSeconds",   0) or 0) / 60),
                "awake_min":  round((sd.get("awakeSleepSeconds", 0) or 0) / 60),
                "score":      sd.get("sleepScores", {}).get("overall", {}).get("value") if isinstance(sd.get("sleepScores"), dict) else None,
                "start":      sd.get("sleepStartTimestampLocal"),
                "end":        sd.get("sleepEndTimestampLocal"),
            }

        # ── Body Battery ────────────────────────────────────────
        bb_data = safe(lambda: api.get_body_battery(ds, ds), [])
        body_battery_end = None
        if bb_data and isinstance(bb_data, list) and len(bb_data) > 0:
            last = bb_data[-1]
            body_battery_end = safe(lambda: last.get("charged") or last.get("bodyBatteryStatLevel"))

        # ── Stress ──────────────────────────────────────────────
        stress_data = safe(lambda: api.get_stress_data(ds), {})
        avg_stress = safe(lambda: stress_data.get("avgStressLevel"))

        garmin_days[ds] = {
            "date":            ds,
            "steps":           steps,
            "resting_hr":      resting_hr,
            "body_battery":    body_battery_end,
            "avg_stress":      avg_stress,
            "sleep":           sleep,
            "activities":      acts,
        }
        print(f"  {ds}: {len(acts)} активности, {steps} стъпки, сън {sleep.get('total_min','?')} мин")

    data["garmin"] = garmin_days
    data["garmin_updated"] = today.isoformat()
    save(data)
    print(f"\ndata.json обновен ✓  ({len(garmin_days)} дни)")

if __name__ == "__main__":
    main()
