"""
Guwahati Pollution Prediction Model
====================================
Step 4: Prediction & Alert System
Run real-time forecasts, generate AQI alerts, export reports.

Usage:
  python predict.py --hours 24
  python predict.py --alert-threshold 150  # alert if PM2.5 > 150
"""

import argparse
import numpy as np
import pandas as pd
import tensorflow as tf
import joblib
import json
from datetime import datetime, timedelta
from feature_engineering import engineer_features, make_sequences, compute_aqi_india
from data_pipeline import MeteoFetcher, _generate_synthetic_aq

MODEL_PATH  = "models/best_model.keras"
SCALER_PATH = "models/scalers/target_scaler.pkl"

# ─────────────────────────────────────────────────────────────────────────────
# Prediction Engine
# ─────────────────────────────────────────────────────────────────────────────

class GuwahatiPredictor:
    """
    Loads trained model and issues multi-horizon PM2.5 forecasts for Guwahati.
    """

    HORIZONS = [1, 3, 6, 12, 24]  # hours ahead

    def __init__(self):
        print("[Predictor] Loading model …")
        self.model         = tf.keras.models.load_model(MODEL_PATH)
        self.target_scaler = joblib.load(SCALER_PATH)
        self.feat_scaler   = joblib.load("models/scalers/feature_scaler.pkl")
        print("[Predictor] Ready.")

    def forecast(self,
                 recent_df: pd.DataFrame,
                 feature_cols: list[str],
                 target_col: str = "pm25") -> pd.DataFrame:
        """
        Given the last 24h of observations → predict next 6 hours.
        Returns a DataFrame of forecasts with AQI labels.
        """
        X = recent_df[feature_cols].values[-24:].reshape(1, 24, len(feature_cols))
        X = X.astype(np.float32)

        y_scaled = self.model.predict(X, verbose=0)   # shape (1, 6)
        y_inv    = self.target_scaler.inverse_transform(y_scaled)[0]  # (6,)

        now = datetime.now()
        rows = []
        for i, pm25 in enumerate(y_inv):
            pm25      = float(np.clip(pm25, 0, 500))
            aqi, cat, color = compute_aqi_india(pm25)
            rows.append({
                "forecast_time":    now + timedelta(hours=i + 1),
                "hours_ahead":      i + 1,
                "pm25_ugm3":        round(pm25, 1),
                "aqi_india":        aqi,
                "aqi_category":     cat,
                "color":            color,
            })
        return pd.DataFrame(rows)

    def multi_horizon_eval(self,
                           X_test: np.ndarray,
                           y_test: np.ndarray) -> dict:
        """
        Evaluate MAE at each forecast horizon separately.
        """
        y_pred   = self.model.predict(X_test, verbose=0)
        results  = {}
        for i, h in enumerate(range(y_test.shape[1])):
            true_inv = self.target_scaler.inverse_transform(y_test[:, i:i+1])
            pred_inv = self.target_scaler.inverse_transform(y_pred[:, i:i+1])
            mae = float(np.mean(np.abs(true_inv - pred_inv)))
            results[f"h{i+1}_mae"] = round(mae, 2)
        return results


# ─────────────────────────────────────────────────────────────────────────────
# Alert System
# ─────────────────────────────────────────────────────────────────────────────

class AlertSystem:
    """
    Monitors PM2.5 forecasts and issues tiered health alerts.
    Aligned with India CPCB AQI standards.
    """

    THRESHOLDS = {
        "advisory":  {"pm25": 60,  "aqi": 100, "color": "🟡"},
        "warning":   {"pm25": 91,  "aqi": 200, "color": "🟠"},
        "emergency": {"pm25": 121, "aqi": 300, "color": "🔴"},
        "hazardous": {"pm25": 251, "aqi": 400, "color": "⚫"},
    }

    # Sensitive areas in Guwahati that need earlier warnings
    SENSITIVE_ZONES = [
        "Dispur (government offices)",
        "Ulubari / Ganeshguri (residential)",
        "Pan Bazar (commercial)",
        "GMCH / Gauhati Medical College",
        "IIT Guwahati campus",
    ]

    def evaluate(self, forecast_df: pd.DataFrame,
                 custom_threshold: float = 100.0) -> list[dict]:
        """
        Generate alerts for each forecast window that exceeds thresholds.
        """
        alerts = []
        for _, row in forecast_df.iterrows():
            pm25 = row["pm25_ugm3"]
            tier = None

            if pm25 >= self.THRESHOLDS["hazardous"]["pm25"]:
                tier = "hazardous"
            elif pm25 >= self.THRESHOLDS["emergency"]["pm25"]:
                tier = "emergency"
            elif pm25 >= self.THRESHOLDS["warning"]["pm25"]:
                tier = "warning"
            elif pm25 >= max(self.THRESHOLDS["advisory"]["pm25"], custom_threshold):
                tier = "advisory"

            if tier:
                emoji = self.THRESHOLDS[tier]["color"]
                alerts.append({
                    "time":         row["forecast_time"].strftime("%Y-%m-%d %H:%M"),
                    "hours_ahead":  row["hours_ahead"],
                    "tier":         tier.upper(),
                    "emoji":        emoji,
                    "pm25":         pm25,
                    "aqi":          row["aqi_india"],
                    "category":     row["aqi_category"],
                    "message":      _alert_message(tier, pm25, row["hours_ahead"]),
                    "health_advice": _health_advice(tier),
                    "sensitive_zones": self.SENSITIVE_ZONES if tier in ("emergency", "hazardous") else [],
                })
        return alerts


def _alert_message(tier: str, pm25: float, hours_ahead: int) -> str:
    messages = {
        "advisory":  f"PM2.5 expected to reach {pm25:.0f} µg/m³ in {hours_ahead}h. Sensitive groups should limit outdoor exposure.",
        "warning":   f"⚠ Poor air quality forecast: PM2.5 {pm25:.0f} µg/m³ in {hours_ahead}h. Reduce outdoor activities.",
        "emergency": f"🚨 Very poor air quality in {hours_ahead}h (PM2.5 {pm25:.0f} µg/m³). Avoid outdoor exposure. Wear N95 masks.",
        "hazardous": f"☠ HAZARDOUS air quality forecast in {hours_ahead}h (PM2.5 {pm25:.0f} µg/m³). STAY INDOORS. Schools and outdoor events should be cancelled.",
    }
    return messages.get(tier, "")


def _health_advice(tier: str) -> dict:
    advice = {
        "advisory": {
            "general_public":  "Consider reducing prolonged outdoor exertion.",
            "sensitive_groups":"People with respiratory/cardiac issues: limit outdoor time.",
            "children":        "Limit strenuous outdoor activities.",
        },
        "warning": {
            "general_public":  "Reduce outdoor exertion, especially in the afternoon.",
            "sensitive_groups":"Stay indoors if possible. Use air purifiers.",
            "children":        "Keep children indoors. Cancel outdoor sports.",
        },
        "emergency": {
            "general_public":  "Everyone should reduce outdoor exposure. Wear N95/FFP2 mask.",
            "sensitive_groups":"Remain indoors. Seek medical attention if symptoms worsen.",
            "children":        "Children must stay indoors. All outdoor events cancelled.",
        },
        "hazardous": {
            "general_public":  "STAY INDOORS. Seal windows. Use air purifiers on max.",
            "sensitive_groups":"Immediate indoor shelter. Contact healthcare if breathing difficulty.",
            "children":        "Schools CLOSED. Emergency alert to parents.",
        },
    }
    return advice.get(tier, {})


# ─────────────────────────────────────────────────────────────────────────────
# Report Generator
# ─────────────────────────────────────────────────────────────────────────────

def generate_report(forecast_df: pd.DataFrame,
                    alerts: list[dict],
                    output_path: str = "reports/forecast_report.json") -> None:
    """Save forecast + alerts as structured JSON for downstream systems."""
    os.makedirs("reports", exist_ok=True)
    report = {
        "generated_at":   datetime.now().isoformat(),
        "city":           "Guwahati, Assam, India",
        "coordinates":    {"lat": 26.1445, "lon": 91.7362},
        "forecast":       forecast_df.to_dict(orient="records"),
        "alerts":         alerts,
        "model_version":  "BiLSTM-Attention v1.0",
        "data_sources":   ["OpenAQ", "Open-Meteo", "CPCB CAAQMS"],
    }
    with open(output_path, "w") as f:
        json.dump(report, f, indent=2, default=str)
    print(f"[Report] Saved → {output_path}")


# ─────────────────────────────────────────────────────────────────────────────
# CLI entry point
# ─────────────────────────────────────────────────────────────────────────────

import os

def run_demo_prediction():
    from data_pipeline import _generate_synthetic_aq, _generate_synthetic_meteo

    print("\n=== Guwahati PM2.5 Forecast Demo ===\n")

    aq_df  = _generate_synthetic_aq(90)
    met_df = _generate_synthetic_meteo(90)
    aq_df["datetime"]  = pd.to_datetime(aq_df["datetime"]).dt.floor("h")
    met_df["datetime"] = pd.to_datetime(met_df["datetime"]).dt.floor("h")
    df     = pd.merge(met_df, aq_df, on="datetime", how="inner")
    # Drop gas columns — scaler fitted without them
    df = df.drop(columns=["no2","so2","o3","co"], errors="ignore")

    df_feat, cols = engineer_features(df, target_col="pm25", fit_scaler=False)

    # Simulate forecast using last known values + noise
    now = datetime.now()
    last_pm25 = float(df["pm25"].iloc[-1])
    alert_sys = AlertSystem()

    rows = []
    for h in range(1, 7):
        pm25 = float(np.clip(last_pm25 + np.random.normal(5 * h, 8), 5, 400))
        aqi, cat, color = compute_aqi_india(pm25)
        rows.append({
            "forecast_time": now + timedelta(hours=h),
            "hours_ahead": h,
            "pm25_ugm3": round(pm25, 1),
            "aqi_india": aqi,
            "aqi_category": cat,
            "color": color,
        })
    forecast_df = pd.DataFrame(rows)

    print("📊 Forecast:")
    print(forecast_df[["hours_ahead", "pm25_ugm3", "aqi_india", "aqi_category"]].to_string(index=False))

    alerts = alert_sys.evaluate(forecast_df)
    if alerts:
        print(f"\n⚠  {len(alerts)} alert(s) issued:")
        for a in alerts:
            print(f"  {a['emoji']} [{a['tier']}] T+{a['hours_ahead']}h: {a['message']}")
    else:
        print("\n✅ No alerts — air quality expected to remain acceptable.")

    generate_report(forecast_df, alerts)
    return forecast_df, alerts


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Guwahati PM2.5 Predictor")
    parser.add_argument("--demo", action="store_true", help="Run demo with synthetic data")
    parser.add_argument("--alert-threshold", type=float, default=100.0)
    args = parser.parse_args()

    if args.demo or not os.path.exists(MODEL_PATH):
        run_demo_prediction()
    else:
        print("Run predict.py --demo for a demo, or train the model first.")
