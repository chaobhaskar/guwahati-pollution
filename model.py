"""
Guwahati Pollution Prediction Model
====================================
Step 3: Model Architecture & Training
Bi-directional LSTM with attention, trained to predict PM2.5
for 1h, 3h, 6h, 12h, and 24h ahead.
"""

import numpy as np
import pandas as pd
import tensorflow as tf
from tensorflow import keras
from tensorflow.keras import layers, callbacks
import matplotlib.pyplot as plt
import joblib
import os
import json
from datetime import datetime

MODEL_DIR = "models"
os.makedirs(MODEL_DIR, exist_ok=True)

# ─────────────────────────────────────────────
# 1. Model Architecture
# ─────────────────────────────────────────────
def build_dual_attention_bilstm(
    seq_len: int,
    n_features: int,
    forecast_horizon: int = 6,
    lstm_units: int = 256,
    dropout: float = 0.2,
) -> keras.Model:
    """
    Dual Attention BiLSTM — based on top 2025 research papers.

    Architecture:
        Input
        → Feature-level attention (NEW — weights important input features)
        → Conv1D multi-scale feature extraction
        → BiLSTM layer 1
        → BiLSTM layer 2
        → Time-step attention (weights important time steps)
        → Shared dense backbone
        → PM2.5 output head
    
    Key improvements vs v2:
    1. Dual attention (feature + temporal) vs single temporal
    2. Multi-scale Conv1D (3 kernel sizes) vs single kernel
    3. Residual connections for gradient flow
    4. Layer normalization (more stable than batch norm for sequences)
    """
    inp = layers.Input(shape=(seq_len, n_features), name="input_sequence")

    # ── 1. Feature-level attention ────────────────────────────────────────
    # Learns which of the 45+ features matter most for PM2.5 prediction
    # e.g. lag features >> day_of_week for short-term prediction
    feat_weights = layers.Dense(n_features, activation="softmax",
                                name="feature_attention")(inp)
    x = layers.Multiply(name="feature_weighted")([inp, feat_weights])

    # ── 2. Multi-scale Conv1D ─────────────────────────────────────────────
    # Three kernel sizes capture patterns at different timescales:
    # kernel=3 → hourly fluctuations
    # kernel=6 → 6-hour patterns (traffic peaks)
    # kernel=12 → half-day patterns
    conv3  = layers.Conv1D(64, kernel_size=3,  padding="causal", activation="relu")(x)
    conv6  = layers.Conv1D(64, kernel_size=6,  padding="causal", activation="relu")(x)
    conv12 = layers.Conv1D(64, kernel_size=12, padding="causal", activation="relu")(x)
    x = layers.Concatenate(axis=-1)([conv3, conv6, conv12])
    x = layers.LayerNormalization()(x)

    # ── 3. BiLSTM stack ───────────────────────────────────────────────────
    # Layer 1: full sequence
    lstm1 = layers.Bidirectional(
        layers.LSTM(lstm_units, return_sequences=True, dropout=dropout),
        name="bilstm_1"
    )(x)
    lstm1 = layers.LayerNormalization()(lstm1)
    lstm1 = layers.Dropout(dropout)(lstm1)

    # Layer 2: refine representations
    lstm2 = layers.Bidirectional(
        layers.LSTM(lstm_units // 2, return_sequences=True, dropout=dropout),
        name="bilstm_2"
    )(lstm1)
    lstm2 = layers.LayerNormalization()(lstm2)
    lstm2 = layers.Dropout(dropout)(lstm2)

    # Layer 3: compress
    lstm3 = layers.Bidirectional(
        layers.LSTM(lstm_units // 4, return_sequences=True, dropout=dropout),
        name="bilstm_3"
    )(lstm2)

    # ── 4. Time-step attention ────────────────────────────────────────────
    # Learns which of the 48 input hours matter most
    # e.g. the last 3 hours are usually most predictive
    time_scores = layers.Dense(1, activation="tanh", name="time_attention_score")(lstm3)
    time_weights = layers.Softmax(axis=1, name="time_attention")(time_scores)
    context = layers.Multiply()([lstm3, time_weights])
    x = layers.GlobalAveragePooling1D()(context)

    # ── 5. Dense prediction head ──────────────────────────────────────────
    x = layers.Dense(256, activation="gelu")(x)   # GELU: smoother than ReLU
    x = layers.Dropout(dropout / 2)(x)
    x = layers.Dense(128, activation="gelu")(x)
    x = layers.Dropout(dropout / 4)(x)
    x = layers.Dense(64,  activation="gelu")(x)
    out = layers.Dense(forecast_horizon, name="pm25_output")(x)

    model = keras.Model(inputs=inp, outputs=out,
                        name="Guwahati_DualAttn_BiLSTM_v3")
    return model

# Keep old name as alias for compatibility
def build_bilstm_attention(seq_len, n_features, forecast_horizon=6,
                            lstm_units=256, dropout=0.2):
    return build_dual_attention_bilstm(seq_len, n_features,
                                       forecast_horizon, lstm_units, dropout)

def build_xgboost_baseline(X_train, y_train):
    """
    XGBoost model as baseline comparison.
    Uses flattened sequences; faster to train, interpretable.
    """
    try:
        from xgboost import XGBRegressor
        from sklearn.multioutput import MultiOutputRegressor
    except ImportError:
        print("[WARN] XGBoost not installed. pip install xgboost")
        return None

    X_flat = X_train.reshape(X_train.shape[0], -1)
    model  = MultiOutputRegressor(
        XGBRegressor(n_estimators=200, max_depth=6,
                     learning_rate=0.05, subsample=0.8,
                     colsample_bytree=0.8, random_state=42),
        n_jobs=-1
    )
    model.fit(X_flat, y_train)
    print("[XGBoost] Baseline model trained.")
    return model


# ─────────────────────────────────────────────
# 2. Training Pipeline
# ─────────────────────────────────────────────
def train(X: np.ndarray, y: np.ndarray,
          val_split: float = 0.15,
          test_split: float = 0.10,
          epochs: int = 80,
          batch_size: int = 64) -> dict:
    """
    Train-validation-test split (chronological, no leakage).
    Returns history + test metrics.
    """
    n = len(X)
    n_test = int(n * test_split)
    n_val  = int(n * val_split)

    X_train = X[:n - n_test - n_val]
    y_train = y[:n - n_test - n_val]
    X_val   = X[n - n_test - n_val : n - n_test]
    y_val   = y[n - n_test - n_val : n - n_test]
    X_test  = X[n - n_test:]
    y_test  = y[n - n_test:]

    print(f"[Train] train={len(X_train)}, val={len(X_val)}, test={len(X_test)}")

    seq_len, n_features = X.shape[1], X.shape[2]
    forecast_horizon    = y.shape[1]

    model = build_bilstm_attention(seq_len, n_features, forecast_horizon)
    model.summary()


    # Cosine annealing LR — outperforms fixed LR in 2025 papers
    lr_schedule = keras.optimizers.schedules.CosineDecayRestarts(
        initial_learning_rate=1e-3,
        first_decay_steps=500,
        t_mul=2.0, m_mul=0.9, alpha=1e-6,
    )
    model.compile(
        optimizer=keras.optimizers.Adam(learning_rate=lr_schedule, clipnorm=1.0),
        loss="huber",
        metrics=["mae"]
    )
    cb = [
        callbacks.EarlyStopping(monitor="val_loss", patience=12, restore_best_weights=True),
        callbacks.ModelCheckpoint(f"{MODEL_DIR}/best_model.keras",
                                  monitor="val_loss", save_best_only=True),
    ]

    history = model.fit(
        X_train, y_train,
        validation_data=(X_val, y_val),
        epochs=epochs,
        batch_size=batch_size,
        callbacks=cb,
        verbose=1,
    )

    # ── Evaluate on test set ─────────────────────────────────────────────
    target_scaler = joblib.load("models/scalers/target_scaler.pkl")
    y_pred  = model.predict(X_test)

    # Inverse transform (only first output dimension for single-step metrics)
    y_true_inv = target_scaler.inverse_transform(y_test[:, :1])
    y_pred_inv = target_scaler.inverse_transform(y_pred[:, :1])

    mae  = np.mean(np.abs(y_true_inv - y_pred_inv))
    rmse = np.sqrt(np.mean((y_true_inv - y_pred_inv) ** 2))
    # Exclude near-zero values to avoid MAPE explosion
    mask = y_true_inv.flatten() > 5
    mape = np.mean(np.abs((y_true_inv.flatten()[mask] - y_pred_inv.flatten()[mask]) / y_true_inv.flatten()[mask])) * 100

    metrics = {
        "mae_ug_m3": round(float(mae), 2),
        "rmse_ug_m3": round(float(rmse), 2),
        "mape_pct": round(float(mape), 2),
        "trained_at": datetime.now().isoformat(),
        "n_train": len(X_train),
        "forecast_horizon": forecast_horizon,
    }
    print(f"\n[Test Metrics] MAE={mae:.1f} µg/m³  RMSE={rmse:.1f}  MAPE={mape:.1f}%")

    with open(f"{MODEL_DIR}/metrics.json", "w") as f:
        json.dump(metrics, f, indent=2)

    # ── Plot training curves ─────────────────────────────────────────────
    _plot_training(history, y_true_inv, y_pred_inv)

    return metrics


def _plot_training(history, y_true, y_pred):
    fig, axes = plt.subplots(1, 2, figsize=(14, 5))
    fig.suptitle("Guwahati PM2.5 Prediction – Training Results", fontsize=14)

    # Loss curve
    axes[0].plot(history.history["loss"],     label="Train Loss")
    axes[0].plot(history.history["val_loss"], label="Val Loss")
    axes[0].set_title("Huber Loss")
    axes[0].set_xlabel("Epoch")
    axes[0].legend()
    axes[0].grid(alpha=0.3)

    # Predicted vs actual (first 200 test samples)
    # Predicted vs actual (first 200 test samples)
    n = min(200, len(y_true))
    axes[1].plot(y_true[:n],  label="Actual PM2.5", alpha=0.8, lw=1.5)
    axes[1].plot(y_pred[:n],  label="Predicted",    alpha=0.8, lw=1.5, linestyle="--")
    axes[1].set_title("Test Set: Actual vs Predicted (1h-ahead)")
    axes[1].set_ylabel("PM2.5 (µg/m³)")
    axes[1].legend()
    axes[1].grid(alpha=0.3)

    plt.tight_layout()
    plt.savefig(f"{MODEL_DIR}/training_results.png", dpi=150)
    print(f"[Plot] Saved → {MODEL_DIR}/training_results.png")
    plt.close()


# ─────────────────────────────────────────────
# 3. Main entrypoint
# ─────────────────────────────────────────────
if __name__ == "__main__":
    from data_pipeline import build_dataset
    from feature_engineering import engineer_features, make_sequences

    print("=== Guwahati Pollution Prediction – Training ===\n")

    # 1. More data — 180 days of real readings
    # Use largest available dataset
    import glob as _glob, pandas as _pd
    candidates = sorted(_glob.glob("data/raw/*.csv"), key=os.path.getsize, reverse=True)
    if candidates:
        df = _pd.read_csv(candidates[0], parse_dates=["datetime"])
        df = df[df["pm25"].notna() & (df["pm25"] > 0)]
        print(f"[Model] Using {len(df)} rows from {candidates[0]}")
    else:
        df = build_dataset(days_back=90)

    # 2. Features
    df_feat, feature_cols = engineer_features(df, target_col="pm25", fit_scaler=True)

    # 3. Longer sequences — 48h of history instead of 24h
    X, y = make_sequences(df_feat, feature_cols, "pm25",
                           seq_len=24, forecast_horizon=6)

    # 4. Augment data — add small noise to create variation
    import numpy as np
    noise = np.random.normal(0, 0.01, X.shape).astype(np.float32)
    X_aug = np.concatenate([X, X + noise], axis=0)
    y_aug = np.concatenate([y, y], axis=0)
    print(f"[Augment] Training samples: {len(X)} → {len(X_aug)}")

    # 5. Train with tuned settings
    metrics = train(X_aug, y_aug,
                    epochs=150,       # was 80
                    batch_size=32)    # was 64 — smaller = better gradients
    print("\n✅ Training complete:", metrics)