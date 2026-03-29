#!/usr/bin/env python3
"""
Guwahati AQI — Automated Daily Data Collector
===============================================
Runs every day at 6am via cron or launchd.
Fetches fresh sensor data, retrains model, pushes to GitHub.

Setup:
    chmod +x auto_collect.py
    crontab -e
    Add: 0 6 * * * cd ~/Desktop/guwahati-pollution && source venv/bin/activate && python auto_collect.py
"""

import os
import sys
import json
import subprocess
import pandas as pd
import numpy as np
import requests
from datetime import datetime, timedelta
import glob
import joblib
import logging

# ── Logging ──────────────────────────────────────────────────────────────────
logging.basicConfig(
    filename="logs/auto_collect.log",
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S"
)
log = logging.getLogger()
os.makedirs("logs", exist_ok=True)

def run(cmd):
    result = subprocess.run(cmd, shell=True, capture_output=True, text=True)
    if result.returncode != 0:
        log.warning(f"Command failed: {cmd}\n{result.stderr}")
    return result.stdout.strip()

def fetch_sensor(sensor_id, param, days_back=1, key=""):
    """Fetch last N days of hourly data from OpenAQ."""
    url = f"https://api.openaq.org/v3/sensors/{sensor_id}/hours"
    date_from = (datetime.utcnow() - timedelta(days=days_back)).strftime("%Y-%m-%dT%H:%M:%SZ")
    headers = {"X-API-Key": key}
    rows = []
    page = 1
    while True:
        r = requests.get(url, params={"datetime_from": date_from, "limit": 1000, "page": page},
                        headers=headers, timeout=30)
        if r.status_code != 200:
            break
        results = r.json().get("results", [])
        if not results:
            break
        for rec in results:
            rows.append({
                "datetime": pd.to_datetime(rec["period"]["datetimeFrom"]["utc"]).tz_localize(None),
                param: rec["value"]
            })
        page += 1
    return pd.DataFrame(rows)

def fetch_weather(days_back=1):
    """Fetch fresh weather from Open-Meteo archive."""
    end   = datetime.utcnow().date()
    start = end - timedelta(days=days_back)
    r = requests.get("https://archive-api.open-meteo.com/v1/archive", params={
        "latitude": 26.1445, "longitude": 91.7362,
        "start_date": str(start), "end_date": str(end),
        "hourly": "temperature_2m,relative_humidity_2m,wind_speed_10m,wind_direction_10m,surface_pressure,precipitation,boundary_layer_height,shortwave_radiation,dewpoint_2m",
        "timezone": "Asia/Kolkata",
    }, timeout=30)
    df = pd.DataFrame(r.json()["hourly"])
    df.rename(columns={"time": "datetime"}, inplace=True)
    df["datetime"] = pd.to_datetime(df["datetime"])
    return df

def update_dataset():
    """Fetch new data and append to existing CSV."""
    log.info("=== Starting daily data collection ===")
    key = os.environ.get("OPENAQ_API_KEY", "a8dd75918c15a522ba6eaca66bf8e690ba38718f4f5f5d520d53e87b85eec2e2")

    # Load existing data
    files = sorted(glob.glob("data/raw/*.csv"), key=os.path.getmtime, reverse=True)
    if files:
        existing = pd.read_csv(files[0], parse_dates=["datetime"])
        last_date = existing["datetime"].max()
        days_needed = max(1, (datetime.now() - last_date).days + 1)
        log.info(f"Existing data until {last_date}. Fetching {days_needed} days.")
    else:
        existing = pd.DataFrame()
        days_needed = 90
        log.info("No existing data. Fetching 90 days.")

    # Fetch new AQ data
    aq_dfs = []
    sensors = [(12235761,"pm25"),(12235760,"pm10")]
    for sid, param in sensors:
        try:
            df = fetch_sensor(sid, param, days_back=days_needed, key=key)
            if not df.empty:
                df["datetime"] = df["datetime"].dt.floor("h")
                aq_dfs.append(df)
                log.info(f"Fetched {len(df)} rows for {param}")
        except Exception as e:
            log.error(f"Failed to fetch {param}: {e}")

    if not aq_dfs:
        log.error("No AQ data fetched. Aborting.")
        return False

    # Merge AQ data
    aq_merged = aq_dfs[0]
    for df in aq_dfs[1:]:
        aq_merged = pd.merge(aq_merged, df, on="datetime", how="outer")
    aq_merged = aq_merged.groupby("datetime").mean().reset_index()

    # Fetch weather
    try:
        weather = fetch_weather(days_back=days_needed)
        weather["datetime"] = pd.to_datetime(weather["datetime"]).dt.floor("h")
    except Exception as e:
        log.error(f"Weather fetch failed: {e}")
        return False

    # Merge AQ + weather
    new_data = pd.merge(weather, aq_merged, on="datetime", how="left")

    # Clean zeros
    for col in ["pm25", "pm10"]:
        if col in new_data.columns:
            new_data.loc[new_data[col] <= 0, col] = np.nan
            new_data[col] = new_data[col].ffill(limit=3).bfill()

    # Combine with existing
    if not existing.empty:
        combined = pd.concat([existing, new_data])
        combined = combined.drop_duplicates(subset=["datetime"])
        combined = combined.sort_values("datetime").reset_index(drop=True)
        # Keep last 365 days
        cutoff = datetime.now() - timedelta(days=365)
        combined = combined[combined["datetime"] >= cutoff]
    else:
        combined = new_data

    # Save
    out_path = "data/raw/guwahati_merged_365d.csv"
    combined.to_csv(out_path, index=False)
    log.info(f"Saved {len(combined)} rows to {out_path}")
    print(f"[AutoCollect] {len(combined)} rows saved. Latest: {combined['datetime'].max()}")
    return True

def retrain_model():
    """Retrain model on fresh data."""
    log.info("Starting model retraining...")
    print("[AutoCollect] Retraining model...")
    result = subprocess.run(
        [sys.executable, "model.py"],
        capture_output=True, text=True, timeout=3600
    )
    if result.returncode == 0:
        log.info("Model retrained successfully")
        print("[AutoCollect] Retraining complete!")
        return True
    else:
        log.error(f"Retraining failed:\n{result.stderr[-500:]}")
        print(f"[AutoCollect] Retraining failed: {result.stderr[-200:]}")
        return False

def push_to_github():
    """Commit and push fresh data to GitHub."""
    log.info("Pushing to GitHub...")
    run("git add -f data/raw/*.csv models/metrics.json")
    run(f'git commit -m "Auto-update: {datetime.now().strftime("%Y-%m-%d %H:%M")} IST"')
    result = run("git push")
    log.info(f"Git push result: {result}")
    print(f"[AutoCollect] Pushed to GitHub!")

def send_alert_if_needed():
    """Check forecast and log if poor air quality expected."""
    try:
        files = sorted(glob.glob("data/raw/*.csv"), key=os.path.getmtime, reverse=True)
        df = pd.read_csv(files[0], parse_dates=["datetime"])
        latest_pm25 = df["pm25"].dropna().iloc[-1]
        if latest_pm25 > 120:
            msg = f"ALERT: PM2.5 = {latest_pm25:.1f} ug/m3 — Poor air quality in Guwahati"
            log.warning(msg)
            print(f"[AutoCollect] {msg}")
    except Exception as e:
        log.error(f"Alert check failed: {e}")

if __name__ == "__main__":
    print(f"\n[AutoCollect] Starting at {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} IST")

    # Step 1: Collect fresh data
    if update_dataset():
        print("[AutoCollect] Data collection successful")
    else:
        print("[AutoCollect] Data collection failed — using existing data")

    # Step 2: Check for alerts
    send_alert_if_needed()

    # Step 3: Retrain (only if --retrain flag passed)
    if "--retrain" in sys.argv:
        retrain_model()

    # Step 4: Push to GitHub
    if "--push" in sys.argv:
        push_to_github()

    print(f"[AutoCollect] Done at {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} IST\n")
