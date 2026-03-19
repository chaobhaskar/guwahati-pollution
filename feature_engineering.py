"""
Guwahati Pollution Prediction Model
====================================
Step 2: Feature Engineering
Guwahati-specific transformations that dramatically improve model accuracy.

Key local factors:
  • Brahmaputra valley bowl → poor dispersion in winter (low BLH)
  • Monsoon washout effect (Jun–Sep) → strong seasonal signal
  • Bihu festival burning (Apr & Oct) → acute spike events
  • NH-27/NH-17 traffic peaks (7–9am, 5–8pm IST)
  • Brick kilns (Nov–May) → elevated SO2/PM10
  • Temperature inversions in winter mornings
"""

import pandas as pd
import numpy as np
from sklearn.preprocessing import RobustScaler
from sklearn.ensemble import RandomForestRegressor
from sklearn.experimental import enable_iterative_imputer
from sklearn.impute import IterativeImputer
import joblib
import os

SCALER_DIR = "models/scalers"

def rf_impute(df: pd.DataFrame) -> pd.DataFrame:
    """
    Replace simple ffill with Random Forest imputation.
    Far more accurate for sensor dropout gaps — used in top 2025 papers.
    Imputes based on relationships between all numeric columns.
    """
    print("[Impute] Running Random Forest imputation...")
    numeric_cols = df.select_dtypes(include=[np.number]).columns.tolist()
    
    # Remove datetime-derived columns that shouldn't be imputed
    impute_cols = [c for c in numeric_cols if c not in 
                   ["hour","day_of_week","month","day_of_year"]]
    
    before_nulls = df[impute_cols].isna().sum().sum()
    if before_nulls == 0:
        print("[Impute] No missing values found.")
        return df
    
    imputer = IterativeImputer(
        estimator=RandomForestRegressor(
            n_estimators=50,
            max_depth=8,
            random_state=42,
            n_jobs=-1
        ),
        max_iter=5,
        random_state=42,
        verbose=0
    )
    df_copy = df.copy()
    df_copy[impute_cols] = imputer.fit_transform(df_copy[impute_cols])
    
    after_nulls = df_copy[impute_cols].isna().sum().sum()
    print(f"[Impute] Nulls before: {before_nulls} → after: {after_nulls}")
    return df_copy

os.makedirs(SCALER_DIR, exist_ok=True)

# Guwahati-specific Bihu dates (approximate, adjust yearly)
BIHU_WINDOWS = [
    ("2023-04-13", "2023-04-17"),  # Bohag (Rongali) Bihu
    ("2023-10-18", "2023-10-22"),  # Kongali Bihu
    ("2024-01-15", "2024-01-19"),  # Bhogali Bihu
    ("2024-04-13", "2024-04-17"),
    ("2025-01-15", "2025-01-19"),
    ("2025-04-13", "2025-04-17"),
]

DIWALI_WINDOWS = [
    ("2023-11-12", "2023-11-14"),
    ("2024-11-01", "2024-11-03"),
]


def add_fourier_features(df: pd.DataFrame,
                         col: str = "pm25",
                         periods: list = [24, 168]) -> pd.DataFrame:
    """
    Add Fourier terms for daily and weekly pollution cycles.
    Captures monsoon/winter seasonality the LSTM misses.
    From: Springer 2025 hybrid decomposition paper.
    """
    t = np.arange(len(df))
    for period in periods:
        df[f"fourier_sin_{period}"] = np.sin(2 * np.pi * t / period)
        df[f"fourier_cos_{period}"] = np.cos(2 * np.pi * t / period)
    print(f"[Fourier] Added {len(periods)*2} decomposition features")
    return df

def engineer_features(df: pd.DataFrame,
                       target_col: str = "pm25",
                       fit_scaler: bool = True) -> tuple[pd.DataFrame, list[str]]:
    """
    Full feature engineering pipeline.

    Parameters
    ----------
    df          : merged DataFrame from data_pipeline.build_dataset()
    target_col  : pollutant to predict
    fit_scaler  : if True, fit+save scalers; else load pre-fitted scalers

    Returns
    -------
    df_feat     : DataFrame with all engineered features
    feature_cols: list of column names to use as model input
    """
    df = df.copy()
    df["datetime"] = pd.to_datetime(df["datetime"])
    df = df.sort_values("datetime").reset_index(drop=True)

    # RF imputation for missing values
    df = rf_impute(df)

    # Fourier decomposition for seasonal patterns
    df = add_fourier_features(df, col=target_col, periods=[24, 168])

    # ── 1. Temporal features ────────────────────────────────────────────
    df["hour"]        = df["datetime"].dt.hour
    df["day_of_week"] = df["datetime"].dt.dayofweek   # 0=Mon … 6=Sun
    df["month"]       = df["datetime"].dt.month
    df["day_of_year"] = df["datetime"].dt.dayofyear

    # Cyclical encoding (avoids 23→0 discontinuity)
    df["hour_sin"]    = np.sin(2 * np.pi * df["hour"]        / 24)
    df["hour_cos"]    = np.cos(2 * np.pi * df["hour"]        / 24)
    df["dow_sin"]     = np.sin(2 * np.pi * df["day_of_week"] / 7)
    df["dow_cos"]     = np.cos(2 * np.pi * df["day_of_week"] / 7)
    df["month_sin"]   = np.sin(2 * np.pi * df["month"]       / 12)
    df["month_cos"]   = np.cos(2 * np.pi * df["month"]       / 12)

    # ── 2. Season flags (Guwahati-specific) ─────────────────────────────
    # Monsoon: Jun–Sep | Winter: Nov–Feb | Pre-monsoon: Mar–May | Post-monsoon: Oct
    df["is_monsoon"]       = df["month"].isin([6, 7, 8, 9]).astype(int)
    df["is_winter"]        = df["month"].isin([11, 12, 1, 2]).astype(int)
    df["is_pre_monsoon"]   = df["month"].isin([3, 4, 5]).astype(int)

    # ── 3. Festival/event flags ─────────────────────────────────────────
    df["is_bihu"]   = _date_in_windows(df["datetime"], BIHU_WINDOWS)
    df["is_diwali"] = _date_in_windows(df["datetime"], DIWALI_WINDOWS)

    # ── 4. Traffic proxy (Guwahati peak hours) ─────────────────────────
    # NH-27 / NH-17 / Paltan Bazar congestion peaks
    df["is_morning_peak"]  = df["hour"].isin([7, 8, 9]).astype(int)
    df["is_evening_peak"]  = df["hour"].isin([17, 18, 19, 20]).astype(int)
    df["is_night_low"]     = df["hour"].isin([1, 2, 3, 4]).astype(int)

    # ── 5. Meteorological derived features ──────────────────────────────

    # Wind components (u/v) for directional modeling
    wind_rad         = np.deg2rad(df["wind_direction_10m"])
    df["wind_u"]     = -df["wind_speed_10m"] * np.sin(wind_rad)  # East component
    df["wind_v"]     = -df["wind_speed_10m"] * np.cos(wind_rad)  # North component

    # Dispersion Index: low BLH + low wind = high pollution potential
    # (inspired by SAFAR India model)
    df["dispersion_index"] = (
        df["boundary_layer_height"] * df["wind_speed_10m"]
    ).clip(lower=1)

    df["log_dispersion"]   = np.log1p(df["dispersion_index"])

    # Ventilation coefficient (BLH × wind speed) – standard air quality metric
    df["ventilation_coeff"] = df["boundary_layer_height"] * df["wind_speed_10m"]

    # Temperature inversion proxy: cold+calm+dry = worst dispersion
    df["inversion_risk"] = (
        (df["temperature_2m"] < 15).astype(float) *
        (df["wind_speed_10m"] < 2).astype(float) *
        df["is_winter"]
    )

    # Precipitation washout effect: rain cleans particulates within 3h
    df["precip_washout"] = df["precipitation"].rolling(3, min_periods=1).max()

    # Humidity-PM interaction: high humidity = hygroscopic PM growth
    df["rh_pm_interaction"] = df["relative_humidity_2m"] / 100 * df.get(target_col, 50)

    # ── 6. Lag features (autoregressive) ────────────────────────────────
    # The most predictive features for next-hour PM2.5 are recent values
    for lag in [1, 2, 3, 6, 12, 24]:
        df[f"{target_col}_lag{lag}h"] = df[target_col].shift(lag)

    # Rolling statistics
    for window in [3, 6, 24]:
        df[f"{target_col}_roll{window}h_mean"] = (
            df[target_col].shift(1).rolling(window, min_periods=1).mean()
        )
        df[f"{target_col}_roll{window}h_std"]  = (
            df[target_col].shift(1).rolling(window, min_periods=1).std()
        )

    # 24-hour periodicity (same hour yesterday)
    df[f"{target_col}_same_hour_yest"] = df[target_col].shift(24)

    # ── 7. Multi-pollutant features (if available) ───────────────────────
    for pol in ["pm10", "no2", "so2", "o3", "co"]:
        if pol in df.columns:
            df[f"{pol}_lag1h"] = df[pol].shift(1)
            # Ratio features: PM10/PM2.5 ratio helps identify source type
    if "pm10" in df.columns and "pm25" in df.columns:
        df["pm_ratio"] = (df["pm10"] / df["pm25"].replace(0, np.nan)).clip(1, 10)

    # ── 8. Drop rows with NaN from lag creation ─────────────────────────
    df = df.dropna(subset=[f"{target_col}_lag24h"]).reset_index(drop=True)

    # ── 9. Define feature columns ───────────────────────────────────────
    # Add fourier columns
    fourier_cols = [c for c in df.columns if "fourier_" in c]

    feature_cols = [
        # Temporal
        "hour_sin", "hour_cos", "dow_sin", "dow_cos",
        "month_sin", "month_cos",
        # Season/event
        "is_monsoon", "is_winter", "is_pre_monsoon",
        "is_bihu", "is_diwali",
        # Traffic proxy
        "is_morning_peak", "is_evening_peak", "is_night_low",
        # Meteorology
        "temperature_2m", "relative_humidity_2m",
        "wind_u", "wind_v", "wind_speed_10m",
        "surface_pressure", "precipitation",
        "boundary_layer_height", "log_dispersion", "dewpoint_2m",
        "ventilation_coeff", "inversion_risk", "precip_washout",
        # Lag/rolling
        f"{target_col}_lag1h",  f"{target_col}_lag2h",  f"{target_col}_lag3h",
        f"{target_col}_lag6h",  f"{target_col}_lag12h", f"{target_col}_lag24h",
        f"{target_col}_roll3h_mean",  f"{target_col}_roll6h_mean",
        f"{target_col}_roll24h_mean", f"{target_col}_roll3h_std",
        f"{target_col}_same_hour_yest",
    ]

    # Add available pollutant lags
    for pol in ["pm10", "no2", "so2", "o3", "co"]:
        lag_col = f"{pol}_lag1h"
        if lag_col in df.columns:
            feature_cols.append(lag_col)
    if "pm_ratio" in df.columns:
        feature_cols.append("pm_ratio")

    # Add fourier columns
    fourier_cols = [c for c in df.columns if "fourier_" in c]

    feature_cols = [c for c in feature_cols if c in df.columns]
    feature_cols += [c for c in fourier_cols if c in df.columns]

    # ── 10. Scale features ───────────────────────────────────────────────
    if fit_scaler:
        scaler = RobustScaler()   # robust to PM2.5 spike outliers
        df[feature_cols] = scaler.fit_transform(df[feature_cols])
        joblib.dump(scaler, f"{SCALER_DIR}/feature_scaler.pkl")

        target_scaler = RobustScaler()
        df[[target_col]] = target_scaler.fit_transform(df[[target_col]])
        joblib.dump(target_scaler, f"{SCALER_DIR}/target_scaler.pkl")
        print(f"[Features] Scalers saved → {SCALER_DIR}/")
    else:
        scaler = joblib.load(f"{SCALER_DIR}/feature_scaler.pkl")
        df[feature_cols] = scaler.transform(df[feature_cols])

    print(f"[Features] {len(feature_cols)} features, {len(df)} samples")
    return df, feature_cols


def _date_in_windows(datetime_series: pd.Series,
                     windows: list[tuple[str, str]]) -> pd.Series:
    """Returns 1 if date falls within any (start, end) window."""
    result = pd.Series(0, index=datetime_series.index)
    for start, end in windows:
        mask = (datetime_series >= start) & (datetime_series <= end)
        result = result | mask.astype(int)
    return result


def make_sequences(df: pd.DataFrame,
                   feature_cols: list[str],
                   target_col: str,
                   seq_len: int = 24,
                   forecast_horizon: int = 6) -> tuple:
    """
    Convert time series → 3D sequences for LSTM.
    
    Returns X of shape (samples, seq_len, features)
            y of shape (samples, forecast_horizon)
    """
    X_list, y_list = [], []
    vals_X = df[feature_cols].values
    vals_y = df[target_col].values

    for i in range(len(df) - seq_len - forecast_horizon + 1):
        X_list.append(vals_X[i : i + seq_len])
        y_list.append(vals_y[i + seq_len : i + seq_len + forecast_horizon])

    X = np.array(X_list, dtype=np.float32)
    y = np.array(y_list, dtype=np.float32)
    print(f"[Sequences] X={X.shape}, y={y.shape}")
    return X, y


def compute_aqi_india(pm25_ugm3: float) -> tuple[int, str, str]:
    """
    India CPCB AQI calculation for PM2.5.
    Returns (AQI_value, category, color_hex)
    """
    breakpoints = [
        (0,   30,  0,   50,  "Good",          "#00e400"),
        (31,  60,  51,  100, "Satisfactory",  "#92d400"),
        (61,  90,  101, 200, "Moderate",      "#ffff00"),
        (91,  120, 201, 300, "Poor",          "#ff7e00"),
        (121, 250, 301, 400, "Very Poor",     "#ff0000"),
        (251, 500, 401, 500, "Severe",        "#7e0023"),
    ]
    for bp_lo, bp_hi, aqi_lo, aqi_hi, category, color in breakpoints:
        if bp_lo <= pm25_ugm3 <= bp_hi:
            aqi = round(((aqi_hi - aqi_lo) / (bp_hi - bp_lo)) * (pm25_ugm3 - bp_lo) + aqi_lo)
            return aqi, category, color
    return 500, "Severe", "#7e0023"


if __name__ == "__main__":
    import pandas as pd
    import glob

    files = glob.glob("data/raw/*.csv")
    if not files:
        print("No data found. Running data_pipeline first...")
        from data_pipeline import build_dataset
        df = build_dataset(days_back=90)
    else:
        df = pd.read_csv(files[0], parse_dates=["datetime"])
        print(f"Loaded {len(df)} rows from {files[0]}")

    df_feat, cols = engineer_features(df, target_col="pm25", fit_scaler=True)
    print(f"\nFeature columns ({len(cols)}):")
    for c in cols:
        print(f"  {c}")

    X, y = make_sequences(df_feat, cols, "pm25", seq_len=24, forecast_horizon=6)
    print(f"\nSequences ready: X={X.shape}, y={y.shape}")
