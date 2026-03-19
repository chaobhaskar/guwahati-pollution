"""
Guwahati Pollution Prediction Model
====================================
Step 1: Data Pipeline
Fetches real-time + historical air quality & meteorological data
for Guwahati, Assam (26.14°N, 91.74°E)

Data Sources:
  - OpenAQ API  → PM2.5, PM10, NO2, SO2, O3, CO
  - Open-Meteo  → Temperature, Humidity, Wind, Pressure (free, no key needed)
  - CPCB CAAQMS → Pan Bazar station (Guwahati's main CPCB node)
"""

import requests
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import time
import os
import json

# ─────────────────────────────────────────────
# CONFIG
# ─────────────────────────────────────────────
GUWAHATI_LAT   = 26.1445
GUWAHATI_LON   = 91.7362
DATA_DIR       = "data/raw"
OPENAQ_API_KEY = os.getenv("OPENAQ_API_KEY", "")   # optional, raises rate limit

os.makedirs(DATA_DIR, exist_ok=True)


# ─────────────────────────────────────────────
# 1. OpenAQ – Air Quality
# ─────────────────────────────────────────────
class OpenAQFetcher:
    BASE = "https://api.openaq.org/v3"

    # Real Guwahati sensor IDs (from OpenAQ v3 API)
    SENSORS = {
        "pm25": 12235761,   # Railway Colony PM2.5 µg/m³ (active)
        "pm10": 12235760,   # Railway Colony PM10 µg/m³ (active)
        "pm25b": 3409360,   # IIT Guwahati PM2.5 backup
    }
    GAS_SENSORS = {
        "no2": 12236487,    # Pan Bazaar NO2 ppb (active 2025)
        "so2": 12236491,    # Pan Bazaar SO2 ppb (active 2025)
        "o3":  12236488,    # Pan Bazaar O3 µg/m³ (active 2025)
        "co":  12236485,    # Pan Bazaar CO ppb (active 2025)
    }
    # Conversion factors ppb → µg/m³ at 25°C
    PPB_TO_UGM3 = {
        "no2": 1.88,
        "so2": 2.62,
        "co":  1.145,
        "o3":  1.0,    # already µg/m³
    }

    def __init__(self, api_key: str = ""):
        self.headers = {"X-API-Key": api_key} if api_key else {}

    def fetch_sensor(self, sensor_id: int, parameter: str,
                     days_back: int = 90) -> pd.DataFrame:
        """Fetch hourly data for a single sensor using v3 API."""
        url = f"{self.BASE}/sensors/{sensor_id}/hours"
        date_from = (datetime.utcnow() - timedelta(days=days_back)).strftime(
                     "%Y-%m-%dT%H:%M:%SZ")
        records, page = [], 1

        while True:
            params = {
                "datetime_from": date_from,
                "limit": 1000,
                "page": page,
            }
            r = requests.get(url, params=params,
                             headers=self.headers, timeout=30)
            if r.status_code != 200:
                print(f"[WARN] Sensor {sensor_id} page {page}: "
                      f"status {r.status_code}")
                break
            results = r.json().get("results", [])
            if not results:
                break
            records.extend(results)
            page += 1
            time.sleep(0.3)

        if not records:
            print(f"[WARN] No data for sensor {sensor_id} ({parameter})")
            return pd.DataFrame()

        rows = []
        for rec in records:
            rows.append({
                "datetime":  pd.to_datetime(
                    rec["period"]["datetimeFrom"]["utc"]),
                "parameter": parameter,
                "value":     rec["value"],
            })
        df = pd.DataFrame(rows).sort_values("datetime").reset_index(drop=True)
        print(f"[OpenAQ] {parameter} (sensor {sensor_id}) "
              f"→ {len(df)} rows")
        return df

    def fetch_gas_sensor(self, sensor_id: int, parameter: str,
                        days_back: int = 90) -> pd.DataFrame:
        """Fetch gas sensor data using /measurements endpoint."""
        url = f"{self.BASE}/sensors/{sensor_id}/measurements"
        date_from = (datetime.utcnow() - timedelta(days=days_back)).strftime(
                     "%Y-%m-%dT%H:%M:%SZ")
        records, page = [], 1

        while True:
            params = {"datetime_from": date_from, "limit": 1000, "page": page}
            r = requests.get(url, params=params,
                            headers=self.headers, timeout=30)
            if r.status_code != 200:
                break
            results = r.json().get("results", [])
            if not results:
                break
            records.extend(results)
            page += 1
            time.sleep(0.3)

        if not records:
            print(f"[WARN] No measurements for {parameter} (sensor {sensor_id})")
            return pd.DataFrame()

        rows = []
        for rec in records:
            try:
                rows.append({
                    "datetime":  pd.to_datetime(rec["datetime"]["utc"]),
                    "parameter": parameter,
                    "value":     rec["value"],
                })
            except (KeyError, TypeError):
                continue

        if not rows:
            return pd.DataFrame()

        df = pd.DataFrame(rows)
        df["datetime"] = df["datetime"].dt.floor("h")
        df = (df.groupby(["datetime", "parameter"])["value"]
               .mean().reset_index())
        print(f"[OpenAQ] {parameter} (sensor {sensor_id}) → {len(df)} rows")
        return df

    def fetch_all(self, days_back: int = 90) -> pd.DataFrame:
        """Fetch all pollutants and merge into wide format."""
        all_dfs = []
        for parameter, sensor_id in self.SENSORS.items():
            df = self.fetch_sensor(sensor_id, parameter, days_back)
            if not df.empty:
                all_dfs.append(df)

        for parameter, sensor_id in self.GAS_SENSORS.items():
            df = self.fetch_gas_sensor(sensor_id, parameter, days_back)
            if not df.empty:
                # Convert ppb to µg/m³ where needed
                factor = self.PPB_TO_UGM3.get(parameter, 1.0)
                if factor != 1.0:
                    df["value"] = df["value"] * factor
                    print(f"[Convert] {parameter} ppb → µg/m³ (×{factor})")
                all_dfs.append(df)

        if not all_dfs:
            return pd.DataFrame()

        # Pivot to wide format — one column per pollutant
        combined = pd.concat(all_dfs, ignore_index=True)
        combined["datetime"] = combined["datetime"].dt.floor("h")
        wide = (combined.groupby(["datetime", "parameter"])["value"]
                        .mean()
                        .unstack("parameter")
                        .reset_index())
        wide.columns.name = None
        print(f"[OpenAQ] Combined → {len(wide)} hourly rows, "
              f"columns: {wide.columns.tolist()}")
        return wide

# ─────────────────────────────────────────────
# 2. Open-Meteo – Free Meteorological Data
# ─────────────────────────────────────────────
class MeteoFetcher:
    BASE = "https://archive-api.open-meteo.com/v1/archive"

    def fetch(self, days_back: int = 30) -> pd.DataFrame:
        """
        Pull hourly weather for Guwahati.
        Variables: temp, humidity, wind speed/dir, surface pressure,
                   precipitation, boundary layer height (key for dispersion!)
        """
        end   = datetime.utcnow().date()
        start = end - timedelta(days=days_back)

        params = {
            "latitude":  GUWAHATI_LAT,
            "longitude": GUWAHATI_LON,
            "start_date": str(start),
            "end_date":   str(end),
            "hourly": ",".join([
                "temperature_2m",
                "relative_humidity_2m",
                "wind_speed_10m",
                "wind_direction_10m",
                "surface_pressure",
                "precipitation",
                "boundary_layer_height",
                "dewpoint_2m",   # critical – low BLH traps pollution
                "shortwave_radiation",
            ]),
            "timezone": "Asia/Kolkata",
        }
        r = requests.get(self.BASE, params=params, timeout=30)
        r.raise_for_status()
        data = r.json()["hourly"]

        df = pd.DataFrame(data)
        df.rename(columns={"time": "datetime"}, inplace=True)
        df["datetime"] = pd.to_datetime(df["datetime"])
        print(f"[Meteo] Fetched {len(df)} hourly rows "
              f"({start} → {end})")
        return df

    def fetch_forecast(self, days_ahead: int = 5) -> pd.DataFrame:
        """Pull weather forecast for future pollution prediction."""
        url = "https://api.open-meteo.com/v1/forecast"
        params = {
            "latitude":  GUWAHATI_LAT,
            "longitude": GUWAHATI_LON,
            "hourly": ",".join([
                "temperature_2m", "relative_humidity_2m",
                "wind_speed_10m", "wind_direction_10m",
                "surface_pressure", "precipitation",
                "boundary_layer_height",
                "dewpoint_2m",
            ]),
            "forecast_days": days_ahead,
            "timezone": "Asia/Kolkata",
        }
        r = requests.get(url, params=params, timeout=30)
        r.raise_for_status()
        data = r.json()["hourly"]
        df = pd.DataFrame(data)
        df.rename(columns={"time": "datetime"}, inplace=True)
        df["datetime"] = pd.to_datetime(df["datetime"])
        print(f"[Meteo Forecast] {len(df)} rows for next {days_ahead} days")
        return df


# ─────────────────────────────────────────────
# 3. Merge & Save
# ─────────────────────────────────────────────

def clean_dataset(df):
    """Fill gaps and remove bad values before training."""
    import pandas as pd
    import numpy as np

    # Forward fill gaps up to 3 hours (sensor dropout)
    df['pm25'] = df['pm25'].ffill(limit=3)
    df['pm10'] = df['pm10'].ffill(limit=3)

    # Interpolate remaining gaps
    df['pm25'] = df['pm25'].interpolate(method='linear', limit=6)
    df['pm10'] = df['pm10'].interpolate(method='linear', limit=6)

    # Fill remaining with rolling median
    df['pm25'] = df['pm25'].fillna(df['pm25'].rolling(24, min_periods=1).median())
    df['pm10'] = df['pm10'].fillna(df['pm10'].rolling(24, min_periods=1).median())

    # Remove physically impossible values
    df.loc[df['pm25'] < 0, 'pm25'] = np.nan
    df.loc[df['pm25'] > 500, 'pm25'] = np.nan
    df.loc[df['pm10'] < 0, 'pm10'] = np.nan
    df.loc[df['pm10'] > 600, 'pm10'] = np.nan

    # Final forward/back fill for any remaining NaN
    df['pm25'] = df['pm25'].ffill().bfill()
    df['pm10'] = df['pm10'].ffill().bfill()

    # Remove zero readings (sensor offline, not real air quality)
    df.loc[df['pm25'] == 0, 'pm25'] = np.nan
    df.loc[df['pm10'] == 0, 'pm10'] = np.nan
    df['pm25'] = df['pm25'].ffill().bfill()
    df['pm10'] = df['pm10'].ffill().bfill()
    print(f'[Clean] pm25 NaN after cleaning: {df["pm25"].isna().sum()}')
    print(f'[Clean] pm10 NaN after cleaning: {df["pm10"].isna().sum()}')
    return df
def build_dataset(days_back: int = 90) -> pd.DataFrame:
    aq_fetcher  = OpenAQFetcher(OPENAQ_API_KEY)
    met_fetcher = MeteoFetcher()

    # --- Real AQ data from Guwahati sensors ---
    print("[Pipeline] Fetching real AQ data from Guwahati sensors...")
    aq_df = aq_fetcher.fetch_all(days_back=days_back)

    if aq_df.empty:
        print("[WARN] No AQ data fetched. Using synthetic fallback.")
        aq_df = _generate_synthetic_aq(days_back)

    # --- Meteorological data ---
    try:
        met_df = met_fetcher.fetch(days_back=days_back)
    except Exception as e:
        print(f"[WARN] Meteo fetch failed: {e}. Using synthetic meteo.")
        met_df = _generate_synthetic_meteo(days_back)

    # --- Merge ---
    aq_df["datetime"]  = pd.to_datetime(aq_df["datetime"]).dt.tz_localize(None).dt.floor("h")
    met_df["datetime"] = pd.to_datetime(met_df["datetime"]).dt.tz_localize(None).dt.floor("h")
    merged = pd.merge(met_df, aq_df, on="datetime", how="left")

    out_path = f"{DATA_DIR}/guwahati_merged_{days_back}d.csv"
    merged = clean_dataset(merged)
    merged.to_csv(out_path, index=False)
    print(f"[Pipeline] Saved {len(merged)} rows → {out_path}")
    return merged

# ─────────────────────────────────────────────
# 4. Synthetic data generator (offline/demo)
# ─────────────────────────────────────────────
def _generate_synthetic_aq(days: int) -> pd.DataFrame:
    """
    Realistic synthetic AQ for Guwahati based on seasonal/diurnal patterns.
    PM2.5 baseline ~60–120 µg/m³ (winter) / 30–60 (monsoon).
    """
    rng   = np.random.default_rng(42)
    hours = pd.date_range(end=datetime.now(), periods=days * 24, freq="h", tz="Asia/Kolkata")

    def diurnal(h): return np.sin((h - 7) * np.pi / 12) * 0.4 + 1   # peak 7am/7pm

    h_arr   = hours.hour.values
    m_arr   = hours.month.values
    # Season factor: high in Nov-Feb, low in Jun-Sep (monsoon cleans air)
    season  = np.where((m_arr >= 6) & (m_arr <= 9), 0.4, 1.0)
    base    = 75 * season * np.array([diurnal(h) for h in h_arr])
    noise   = rng.normal(0, 8, len(hours))
    pm25    = np.clip(base + noise, 5, 350)
    pm10    = pm25 * rng.uniform(1.5, 2.0, len(hours))
    no2     = np.clip(40 * season * np.array([diurnal(h) for h in h_arr]) + rng.normal(0, 5, len(hours)), 2, 200)
    so2     = np.clip(15 * season + rng.normal(0, 3, len(hours)), 1, 80)
    o3      = np.clip(30 + 20 * np.sin((h_arr - 14) * np.pi / 12) + rng.normal(0, 4, len(hours)), 5, 100)
    co      = np.clip(1.2 * season * np.array([diurnal(h) for h in h_arr]) + rng.normal(0, 0.2, len(hours)), 0.1, 10)

    return pd.DataFrame({
        "datetime": hours.tz_localize(None),
        "pm25": pm25, "pm10": pm10,
        "no2": no2,   "so2": so2,
        "o3": o3,     "co": co,
    })


def _generate_synthetic_meteo(days: int) -> pd.DataFrame:
    rng   = np.random.default_rng(7)
    hours = pd.date_range(end=datetime.now(), periods=days * 24, freq="h")
    m_arr = hours.month.values
    h_arr = hours.hour.values

    # Guwahati climate: hot humid summers, cool dry winters, heavy monsoon
    temp_base = np.where((m_arr >= 6) & (m_arr <= 9), 30, np.where(m_arr <= 2, 15, 25))
    temp      = temp_base + 4 * np.sin((h_arr - 14) * np.pi / 12) + rng.normal(0, 1, len(hours))
    humidity  = np.where((m_arr >= 6) & (m_arr <= 9), 85, 65) + rng.normal(0, 5, len(hours))
    wind_spd  = np.abs(rng.normal(2.5, 1.5, len(hours)))
    wind_dir  = rng.uniform(0, 360, len(hours))
    pressure  = 1008 + rng.normal(0, 3, len(hours))
    precip    = np.where((m_arr >= 6) & (m_arr <= 9),
                         rng.exponential(2, len(hours)),
                         rng.exponential(0.1, len(hours)))
    blh       = np.where((m_arr >= 6) & (m_arr <= 9), 1800, 600) + \
                400 * np.sin((h_arr - 14) * np.pi / 12) + rng.normal(0, 100, len(hours))

    return pd.DataFrame({
        "datetime": hours,
        "temperature_2m": temp, "relative_humidity_2m": np.clip(humidity, 20, 100),
        "wind_speed_10m": wind_spd, "wind_direction_10m": wind_dir,
        "surface_pressure": pressure, "precipitation": np.clip(precip, 0, None),
        "boundary_layer_height": np.clip(blh, 100, 4000),
        "shortwave_radiation": np.clip(300 * np.sin((h_arr - 6) * np.pi / 12), 0, None),
    })


if __name__ == "__main__":
    df = build_dataset(days_back=90)
    print(df.head())
    print(df.describe())
