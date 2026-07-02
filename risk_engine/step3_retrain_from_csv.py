import numpy as np
import pandas as pd
import os
import pickle

os.makedirs("models", exist_ok=True)

CSV_PATH    = "sessions_converted.csv"
REPORT_PATH = "models/step3_retrain_report.txt"
META_COLS   = ["user_id", "session_id", "timestamp", "label"]

report_lines = []
def log(msg=""):
    print(msg)
    report_lines.append(str(msg))


def main():
    log("=" * 58)
    log("  BehaviorGuard AI — Step 3 (retrain): Train Models")
    log("  Source: sessions_converted.csv (raw features)")
    log("=" * 58)
    log()

    # ── 1. Load data directly from the CSV ────────────────────────────────
    if not os.path.isfile(CSV_PATH):
        log(f"ERROR: {CSV_PATH} not found.")
        return

    df = pd.read_csv(CSV_PATH)
    feature_cols = [c for c in df.columns if c not in META_COLS]
    log(f"Loaded {len(df)} sessions x {len(feature_cols)} features from {CSV_PATH}")
    log(f"Feature columns (in order): {feature_cols}")
    log(f"Users: {sorted(df['user_id'].unique())}")
    log()

    # ── 2. Per-user 80/20 train/test split (stratified so every user ──────
    #      appears in both train and test, matching step3's intent of
    #      evaluating per-user flag rates on held-out sessions)
    rng = np.random.RandomState(42)
    train_idx, test_idx = [], []
    for user, group in df.groupby("user_id"):
        idx = group.index.to_numpy().copy()
        rng.shuffle(idx)
        n_test = max(1, int(round(len(idx) * 0.2)))
        test_idx.extend(idx[:n_test])
        train_idx.extend(idx[n_test:])

    train_df = df.loc[train_idx]
    test_df  = df.loc[test_idx]

    X_train = train_df[feature_cols].values.astype(np.float64)
    X_test  = test_df[feature_cols].values.astype(np.float64)
    users_train = train_df["user_id"].values
    users_test  = test_df["user_id"].values

    log(f"Train : {X_train.shape[0]} sessions x {X_train.shape[1]} features")
    log(f"Test  : {X_test.shape[0]} sessions x {X_test.shape[1]} features")
    log()

    # ── 3. Scale features (StandardScaler) — same as step3 ────────────────
    from sklearn.preprocessing import StandardScaler

    scaler = StandardScaler()
    X_train_scaled = scaler.fit_transform(X_train)
    X_test_scaled  = scaler.transform(X_test)

    X_train_scaled = np.nan_to_num(X_train_scaled, nan=0.0, posinf=0.0, neginf=0.0)
    X_test_scaled  = np.nan_to_num(X_test_scaled,  nan=0.0, posinf=0.0, neginf=0.0)

    with open("models/scaler_web.pkl", "wb") as f:
        pickle.dump(scaler, f)
    log("Saved scaler -> models/scaler_web.pkl")

    # ── 4. Train Isolation Forest — same hyperparameters as step3 ─────────
    log()
    log("Training Isolation Forest...")
    from sklearn.ensemble import IsolationForest

    iso_forest = IsolationForest(
        n_estimators=200,
        contamination=0.05,
        random_state=42,
        n_jobs=-1
    )
    iso_forest.fit(X_train_scaled)

    iso_scores = iso_forest.decision_function(X_test_scaled)
    iso_labels = iso_forest.predict(X_test_scaled)
    n_flagged  = (iso_labels == -1).sum()
    n_normal   = (iso_labels == 1).sum()

    log(f"  Isolation Forest results on test set:")
    log(f"  Normal sessions   : {n_normal}")
    log(f"  Flagged as anomaly: {n_flagged} ({100*n_flagged/len(iso_labels):.1f}%)")
    log()

    with open("models/isolation_forest_web.pkl", "wb") as f:
        pickle.dump(iso_forest, f)
    log("Saved -> models/isolation_forest_web.pkl")

    # ── 5. Train Autoencoder — same architecture as step3 ─────────────────
    log()
    log("Training Autoencoder...")

    import tensorflow as tf
    from tensorflow import keras

    n_features = X_train_scaled.shape[1]

    inputs = keras.Input(shape=(n_features,), name="input")
    x = keras.layers.Dense(32, activation="relu", name="enc_1")(inputs)
    x = keras.layers.Dropout(0.1)(x)
    x = keras.layers.Dense(16, activation="relu", name="enc_2")(x)
    x = keras.layers.Dense(8,  activation="relu", name="bottleneck")(x)
    x = keras.layers.Dense(16, activation="relu", name="dec_1")(x)
    x = keras.layers.Dense(32, activation="relu", name="dec_2")(x)
    outputs = keras.layers.Dense(n_features, activation="linear", name="output")(x)

    autoencoder = keras.Model(inputs, outputs, name="autoencoder")
    autoencoder.compile(optimizer="adam", loss="mse")

    log(f"  Architecture: {n_features} -> 32 -> 16 -> 8 -> 16 -> 32 -> {n_features}")
    log(f"  Total parameters: {autoencoder.count_params():,}")

    early_stop = keras.callbacks.EarlyStopping(
        monitor="val_loss",
        patience=10,
        restore_best_weights=True
    )

    history = autoencoder.fit(
        X_train_scaled, X_train_scaled,
        epochs=100,
        batch_size=16,
        validation_split=0.15,
        callbacks=[early_stop],
        verbose=0
    )

    epochs_run = len(history.history["loss"])
    final_loss = history.history["val_loss"][-1]
    log(f"  Trained for {epochs_run} epochs  |  Final val_loss: {final_loss:.4f}")

    train_reconstructions = autoencoder.predict(X_train_scaled, verbose=0)
    train_errors = np.mean(np.abs(train_reconstructions - X_train_scaled), axis=1)
    threshold    = float(np.percentile(train_errors, 95))

    test_reconstructions = autoencoder.predict(X_test_scaled, verbose=0)
    test_errors = np.mean(np.abs(test_reconstructions - X_test_scaled), axis=1)
    n_ae_flagged = (test_errors > threshold).sum()

    log(f"  Anomaly threshold (95th percentile MAE): {threshold:.4f}")
    log(f"  Test sessions flagged as anomaly        : {n_ae_flagged} "
        f"({100*n_ae_flagged/len(test_errors):.1f}%)")

    autoencoder.save("models/autoencoder_web.keras")
    np.save("models/autoencoder_threshold_web.npy", np.array([threshold]))
    log("Saved -> models/autoencoder_web.keras")
    log("Saved -> models/autoencoder_threshold_web.npy")

    # ── 6. Per-user anomaly check ──────────────────────────────────────────
    log()
    log("Per-user test results (Isolation Forest):")
    log(f"  {'User':12s}  {'Sessions':8s}  {'Flagged':8s}  {'Flag Rate':10s}  Status")
    log("  " + "-" * 55)

    for user in sorted(set(users_test)):
        mask        = users_test == user
        user_flags  = (iso_labels[mask] == -1).sum()
        flag_rate   = user_flags / max(mask.sum(), 1) * 100
        status      = "good" if flag_rate < 50 else "high false positive — check data"
        log(f"  {user:12s}  {mask.sum():8d}  {user_flags:8d}  {flag_rate:9.1f}%  {status}")

    # ── 7. Sanity check: score the training data through the SAME formula
    #      risk_engine.py uses, to confirm genuine sessions land in 'allow'
    log()
    log("Sanity check — scoring TRAIN sessions with risk_engine.py's formula:")
    log("  (genuine sessions should mostly land in allow/stepup, not block)")

    iso_full = iso_forest.decision_function(X_train_scaled)
    iso_risk = np.clip(1.0 - (np.clip(iso_full, -0.5, 0.5) + 0.5) / 1.0, 0, 1)

    recon_full = autoencoder.predict(X_train_scaled, verbose=0)
    mae_full   = np.mean(np.abs(X_train_scaled - recon_full), axis=1)
    ae_risk    = np.clip(mae_full / (2.0 * threshold), 0, 1)

    combined = (0.60 * iso_risk + 0.40 * ae_risk) * 99.0 + 1.0

    bands = {"allow": 0, "stepup": 0, "hold": 0, "block": 0}
    for s in combined:
        if s > 80: bands["block"] += 1
        elif s > 60: bands["hold"] += 1
        elif s > 30: bands["stepup"] += 1
        else: bands["allow"] += 1

    log(f"  Train risk_score range: {combined.min():.2f} - {combined.max():.2f}  "
        f"(mean {combined.mean():.2f})")
    log(f"  Band distribution on TRAIN data: {bands}")
    log("  (some stepup/hold is expected at 5% contamination; block should be rare)")

    # ── 8. Save report ──────────────────────────────────────────────────────
    with open(REPORT_PATH, "w", encoding="utf-8") as f:
        f.write("\n".join(report_lines))

    log()
    log(f"Report saved -> {REPORT_PATH}")
    log()
    log("Retrain complete. New models saved in 'models/'.")


if __name__ == "__main__":
    main()
