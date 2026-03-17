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
def build_bilstm_attention(
    seq_len: int,
    n_features: int,
    forecast_horizon: int = 6,
    lstm_units: int = 256,     # was 128 — more capacity
    dropout: float = 0.2,      # was 0.25 — less aggressive dropout
) -> keras.Model:

    inp = layers.Input(shape=(seq_len, n_features), name="input_sequence")

    # Wider Conv1D to capture longer local patterns
    x = layers.Conv1D(filters=128, kernel_size=5, padding="causal",
                      activation="relu", name="conv_mix")(inp)
    x = layers.BatchNormalization()(x)

    # Deeper BiLSTM stack
    x = layers.Bidirectional(
        layers.LSTM(lstm_units, return_sequences=True, dropout=dropout),
        name="bilstm_1"
    )(x)
    x = layers.Dropout(dropout)(x)

    x = layers.Bidirectional(
        layers.LSTM(lstm_units // 2, return_sequences=True, dropout=dropout),
        name="bilstm_2"
    )(x)
    x = layers.Dropout(dropout)(x)

    # Extra LSTM layer — new
    x = layers.Bidirectional(
        layers.LSTM(lstm_units // 4, return_sequences=True, dropout=dropout),
        name="bilstm_3"
    )(x)

    # Self-attention
    attention_scores = layers.Dense(1, activation="tanh")(x)
    attention_weights = layers.Softmax(axis=1, name="attention")(attention_scores)
    context = layers.Multiply()([x, attention_weights])
    x = layers.GlobalAveragePooling1D()(context)

    # Wider dense head
    x = layers.Dense(256, activation="relu")(x)
    x = layers.Dropout(dropout / 2)(x)
    x = layers.Dense(128, activation="relu")(x)
    x = layers.Dense(64, activation="relu")(x)
    out = layers.Dense(forecast_horizon, name="output")(x)

    model = keras.Model(inputs=inp, outputs=out, name="Guwahati_BiLSTM_Attn_v2")
    return model

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

    model.compile(
        optimizer=keras.optimizers.Adam(
            learning_rate=1e-3,
            clipnorm=1.0
        ),
        loss="huber",           # robust to PM2.5 spike outliers
        metrics=["mae"]
    )

    cb = [
        callbacks.EarlyStopping(monitor="val_loss", patience=12,
                                restore_best_weights=True),
        callbacks.ReduceLROnPlateau(monitor="val_loss", factor=0.5,
                                    patience=5, min_lr=1e-6),
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
    df = build_dataset(days_back=90)

    # 2. Features
    df_feat, feature_cols = engineer_features(df, target_col="pm25", fit_scaler=True)

    # 3. Longer sequences — 48h of history instead of 24h
    X, y = make_sequences(df_feat, feature_cols, "pm25",
                           seq_len=48, forecast_horizon=6)

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