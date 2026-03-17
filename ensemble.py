import numpy as np
import pandas as pd
import joblib
import json
import os
from datetime import datetime
import glob

class EnsemblePredictor:
    """
    Ensemble of 3 models:
    1. BiLSTM (deep patterns)
    2. XGBoost (spike detection)
    3. Prophet (seasonal trends)
    Weighted average based on each model validation performance.
    """

    def __init__(self):
        self.models = {}
        self.weights = {"lstm": 0.75, "xgboost": 0.10, "prophet": 0.15}
        self.target_scaler = None
        self.feature_scaler = None

    def load_scalers(self):
        self.target_scaler = joblib.load("models/scalers/target_scaler.pkl")
        self.feature_scaler = joblib.load("models/scalers/feature_scaler.pkl")

    def train_xgboost(self, X_train, y_train):
        from xgboost import XGBRegressor
        from sklearn.multioutput import MultiOutputRegressor
        print("[XGBoost] Training...")
        X_flat = X_train.reshape(X_train.shape[0], -1)
        model = MultiOutputRegressor(
            XGBRegressor(
                n_estimators=300,
                max_depth=6,
                learning_rate=0.05,
                subsample=0.8,
                colsample_bytree=0.8,
                min_child_weight=3,
                random_state=42,
                n_jobs=-1,
            ), n_jobs=-1
        )
        model.fit(X_flat, y_train)
        self.models["xgboost"] = model
        joblib.dump(model, "models/xgboost_model.pkl")
        print("[XGBoost] Done and saved.")
        return model

    def train_prophet(self, hist_df):
        from prophet import Prophet
        print("[Prophet] Training...")
        df = hist_df[["datetime", "pm25"]].copy()
        df.columns = ["ds", "y"]
        df = df.dropna()
        df["ds"] = pd.to_datetime(df["ds"])
        model = Prophet(
            daily_seasonality=True,
            weekly_seasonality=True,
            yearly_seasonality=True,
            changepoint_prior_scale=0.1,
        )
        model.add_seasonality(name="monsoon", period=365.25/4, fourier_order=5)
        model.fit(df)
        self.models["prophet"] = model
        joblib.dump(model, "models/prophet_model.pkl")
        print("[Prophet] Done and saved.")
        return model

    def load_lstm(self):
        import tensorflow as tf
        if os.path.exists("models/best_model.keras"):
            self.models["lstm"] = tf.keras.models.load_model("models/best_model.keras")
            print("[LSTM] Loaded.")
        else:
            print("[WARN] No LSTM model found. Train model.py first.")

    def predict_xgboost(self, X):
        model = self.models.get("xgboost")
        if model is None:
            return None
        X_flat = X.reshape(X.shape[0], -1)
        y_scaled = model.predict(X_flat)
        return self.target_scaler.inverse_transform(y_scaled)

    def predict_lstm(self, X):
        model = self.models.get("lstm")
        if model is None:
            return None
        y_scaled = model.predict(X, verbose=0)
        return self.target_scaler.inverse_transform(y_scaled)

    def predict_prophet(self, periods=6):
        model = self.models.get("prophet")
        if model is None:
            return None
        future = model.make_future_dataframe(periods=periods, freq="h")
        forecast = model.predict(future)
        return forecast["yhat"].tail(periods).values.reshape(1, -1)

    def predict_ensemble(self, X, periods=6):
        """
        Run all models and combine with weighted average.
        Returns array of shape (n_samples, forecast_horizon)
        """
        predictions = {}
        weights_used = {}

        lstm_pred = self.predict_lstm(X)
        if lstm_pred is not None:
            predictions["lstm"] = lstm_pred
            weights_used["lstm"] = self.weights["lstm"]

        xgb_pred = self.predict_xgboost(X)
        if xgb_pred is not None:
            predictions["xgboost"] = xgb_pred
            weights_used["xgboost"] = self.weights["xgboost"]

        prophet_pred = self.predict_prophet(periods)
        if prophet_pred is not None:
            prophet_full = np.tile(prophet_pred, (X.shape[0], 1))
            predictions["prophet"] = prophet_full
            weights_used["prophet"] = self.weights["prophet"]

        if not predictions:
            raise ValueError("No models available for prediction!")

        # Normalize weights
        total = sum(weights_used.values())
        norm_weights = {k: v/total for k, v in weights_used.items()}

        # Weighted average
        ensemble = np.zeros_like(list(predictions.values())[0])
        for name, pred in predictions.items():
            ensemble += norm_weights[name] * pred
            print(f"  [{name}] weight={norm_weights[name]:.2f} sample_pred={pred[0,0]:.1f}")

        # Hybrid: use XGBoost for spike conditions
        if "xgboost" in predictions and "lstm" in predictions:
            lstm_pred = predictions["lstm"]
            xgb_pred  = predictions["xgboost"]
            # Where LSTM predicts spike > 150, blend more XGBoost
            spike_mask = lstm_pred > 150
            ensemble[spike_mask] = (
                0.4 * lstm_pred[spike_mask] +
                0.6 * xgb_pred[spike_mask]
            )
            n_spikes = spike_mask.sum()
            if n_spikes > 0:
                print(f"  [Hybrid] Applied XGBoost to {n_spikes} spike predictions")

        print(f"  [Ensemble] final={ensemble[0,0]:.1f} µg/m³")
        return np.clip(ensemble, 0, 500)

    def evaluate(self, X_test, y_test):
        """Compare individual models vs ensemble on test set."""
        results = {}
        self.load_scalers()
        y_true = self.target_scaler.inverse_transform(y_test[:, :1])

        for name, pred_fn in [
            ("lstm",     lambda: self.predict_lstm(X_test)),
            ("xgboost",  lambda: self.predict_xgboost(X_test)),
        ]:
            pred = pred_fn()
            if pred is not None:
                mae = float(np.mean(np.abs(y_true - pred[:, :1])))
                results[name] = round(mae, 2)

        ens = self.predict_ensemble(X_test)
        mae_ens = float(np.mean(np.abs(y_true - ens[:, :1])))
        results["ensemble"] = round(mae_ens, 2)

        print("\n=== Model Comparison ===")
        for name, mae in results.items():
            print(f"  {name:12} MAE = {mae} µg/m³")
        print(f"  Best: {min(results, key=results.get)}")

        with open("models/ensemble_metrics.json", "w") as f:
            json.dump(results, f, indent=2)
        return results


def train_ensemble():
    """Full ensemble training pipeline."""
    from data_pipeline import build_dataset
    from feature_engineering import engineer_features, make_sequences

    print("=== Ensemble Training Pipeline ===\n")

    # Load data
    files = sorted(glob.glob("data/raw/*.csv"), key=os.path.getmtime, reverse=True)
    if files:
        df = pd.read_csv(files[0], parse_dates=["datetime"])
        df = df.dropna(subset=["pm25"])
        df = df[df["pm25"] > 0]
        print(f"Loaded {len(df)} rows from {files[0]}")
    else:
        df = build_dataset(days_back=90)

    # Features
    df_feat, feature_cols = engineer_features(df, target_col="pm25", fit_scaler=True)

    # Sequences for LSTM/XGBoost
    X, y = make_sequences(df_feat, feature_cols, "pm25", seq_len=48, forecast_horizon=6)

    # Train/test split
    n = len(X)
    split = int(n * 0.85)
    X_train, X_test = X[:split], X[split:]
    y_train, y_test = y[:split], y[split:]

    ensemble = EnsemblePredictor()
    ensemble.load_scalers()

    # Train XGBoost
    ensemble.train_xgboost(X_train, y_train)

    # Train Prophet on raw historical data
    ensemble.train_prophet(df)

    # Load existing LSTM
    ensemble.load_lstm()

    # Evaluate all models
    print("\n[Evaluating ensemble...]")
    results = ensemble.evaluate(X_test, y_test)

    print("\nEnsemble training complete!")
    print(f"Results saved to models/ensemble_metrics.json")
    return results


if __name__ == "__main__":
    train_ensemble()
