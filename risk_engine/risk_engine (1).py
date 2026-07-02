from flask import Flask, request, jsonify
from flask_cors import CORS
import numpy as np
import pickle
import os
import math
import warnings
warnings.filterwarnings("ignore")

# ── Lazy-load TF only when needed (keeps startup fast) ───────────────────────
_tf = None
def get_tf():
    global _tf
    if _tf is None:
        import tensorflow as tf
        _tf = tf
    return _tf


# ── Model paths ───────────────────────────────────────────────────────────────
BASE_DIR   = os.path.dirname(os.path.abspath(__file__))

SCALER_PATH     = "scaler_web (3).pkl"
ISO_PATH        = "isolation_forest_web (3).pkl"
AE_PATH         = "autoencoder_web (3).keras"
AE_THRESH_PATH  = "autoencoder_threshold_web (3).npy"


# ── Load models once at startup ───────────────────────────────────────────────
print("  Loading scaler …", end=" ", flush=True)
with open(SCALER_PATH, "rb") as f:
    SCALER = pickle.load(f)
print("OK")

print("  Loading Isolation Forest …", end=" ", flush=True)
with open(ISO_PATH, "rb") as f:
    ISO_FOREST = pickle.load(f)
print("OK")

print("  Loading Autoencoder …", end=" ", flush=True)
tf = get_tf()
AUTOENCODER = tf.keras.models.load_model(AE_PATH)
AE_THRESHOLD = float(np.load(AE_THRESH_PATH)[0])
print(f"OK  (threshold={AE_THRESHOLD:.5f})")


# ── Flask app ─────────────────────────────────────────────────────────────────
app = Flask(__name__)
CORS(app)


def safe_mean(lst):
    return round(sum(lst) / len(lst), 4) if lst else 0.0


def safe_std(lst):
    """Sample standard deviation (ddof=1), matching server.py exactly.
    NOT the same as numpy's default np.std() (which uses ddof=0)."""
    if len(lst) < 2:
        return 0.0
    m = sum(lst) / len(lst)
    return round((sum((x - m) ** 2 for x in lst) / (len(lst) - 1)) ** 0.5, 4)


def safe_min(lst):
    return round(min(lst), 4) if lst else 0.0


def safe_max(lst):
    return round(max(lst), 4) if lst else 0.0


def percentile(lst, p):
    """Linear-interpolation percentile, matching server.py exactly
    (equivalent to numpy.percentile's default method)."""
    if not lst:
        return 0.0
    s = sorted(lst)
    idx = (p / 100) * (len(s) - 1)
    lo, hi = int(idx), min(int(idx) + 1, len(s) - 1)
    return round(s[lo] + (idx - lo) * (s[hi] - s[lo]), 4)


def extract_features(events: list) -> np.ndarray:
  
    keydowns  = [e for e in events if e.get("type") == "kd"]
    keyups    = [e for e in events if e.get("type") == "ku"]
    mousemove = [e for e in events if e.get("type") == "mm"]
    clicks    = [e for e in events if e.get("type") == "cl"]
    scrolls   = [e for e in events if e.get("type") == "sc"]

    # ── Keystroke: hold times ─────────────────────────────────────────────
    kd_map, hold_times = {}, []
    for e in keydowns:
        kd_map[e.get("key")] = e.get("ts")
    for e in keyups:
        key = e.get("key")
        if key in kd_map and kd_map[key] is not None and "ts" in e:
            h = e["ts"] - kd_map[key]
            if 0 < h < 2000:
                hold_times.append(h)

    # ── Keystroke: inter-key latency ──────────────────────────────────────
    kd_times = [e["ts"] for e in keydowns if "ts" in e]
    latencies = [kd_times[i] - kd_times[i - 1]
                 for i in range(1, len(kd_times))
                 if 0 < kd_times[i] - kd_times[i - 1] < 2000]

    # ── Typing speed ──────────────────────────────────────────────────────
    typing_speed = 0
    if len(kd_times) >= 2:
        dur = kd_times[-1] - kd_times[0]
        if dur > 0:
            typing_speed = len(kd_times) / (dur / 1000)

    # ── Error rate ────────────────────────────────────────────────────────
    backspaces = sum(1 for e in keydowns if e.get("key") == "Backspace")
    error_rate = backspaces / max(len(keydowns), 1)

    # ── Keystroke rhythm variance (low = bot, high = human) ───────────────
    rhythm_variance = safe_std(latencies)

    # ── Mouse velocity ────────────────────────────────────────────────────
    velocities = []
    for i in range(1, len(mousemove)):
        dt = mousemove[i].get("ts", 0) - mousemove[i - 1].get("ts", 0)
        if dt <= 0:
            continue
        dx = mousemove[i].get("x", 0) - mousemove[i - 1].get("x", 0)
        dy = mousemove[i].get("y", 0) - mousemove[i - 1].get("y", 0)
        velocities.append(math.sqrt(dx * dx + dy * dy) / dt)

    # ── Mouse path curvature ──────────────────────────────────────────────
    curvatures = []
    for i in range(0, len(mousemove) - 5, 5):
        w  = mousemove[i:i + 5]
        xs = [e.get("x", 0) for e in w]
        ys = [e.get("y", 0) for e in w]
        seg  = sum(math.sqrt((xs[j] - xs[j - 1]) ** 2 + (ys[j] - ys[j - 1]) ** 2)
                   for j in range(1, len(w)))
        line = math.sqrt((xs[-1] - xs[0]) ** 2 + (ys[-1] - ys[0]) ** 2)
        if line > 0:
            curvatures.append(seg / line)

    # ── Mouse acceleration ────────────────────────────────────────────────
    accelerations = [abs(velocities[i] - velocities[i - 1])
                      for i in range(1, len(velocities))]

    # ── Click timing ──────────────────────────────────────────────────────
    ct = [e["ts"] for e in clicks if "ts" in e]
    click_intervals = [ct[i] - ct[i - 1] for i in range(1, len(ct))
                        if 0 < ct[i] - ct[i - 1] < 30000]

    # ── Session-level features ────────────────────────────────────────────
    all_ts = [e["ts"] for e in events if "ts" in e]
    session_duration = (max(all_ts) - min(all_ts)) if len(all_ts) >= 2 else 0

    sorted_ev = sorted([e for e in events if "ts" in e], key=lambda e: e["ts"])
    pause_count = sum(1 for i in range(1, len(sorted_ev))
                       if sorted_ev[i]["ts"] - sorted_ev[i - 1]["ts"] > 1000)

    # ── Idle ratio ────────────────────────────────────────────────────────
    idle_time = sum(mousemove[i]["ts"] - mousemove[i - 1]["ts"]
                     for i in range(1, len(mousemove))
                     if mousemove[i].get("ts", 0) - mousemove[i - 1].get("ts", 0) > 500)
    idle_ratio = idle_time / max(session_duration, 1)

    feat = np.array([
        safe_mean(hold_times),                  # hold_mean
        safe_std(hold_times),                   # hold_std
        safe_min(hold_times),                    # hold_min
        safe_max(hold_times),                    # hold_max
        percentile(hold_times, 25),              # hold_p25
        percentile(hold_times, 75),              # hold_p75
        safe_mean(latencies),                    # latency_mean
        safe_std(latencies),                     # latency_std
        safe_min(latencies),                      # latency_min
        safe_max(latencies),                      # latency_max
        round(typing_speed, 4),                  # typing_speed
        round(error_rate, 4),                    # error_rate
        rhythm_variance,                          # rhythm_variance
        float(len(keydowns)),                    # key_count
        float(backspaces),                        # backspace_count
        safe_mean(velocities),                    # mouse_vel_mean
        safe_std(velocities),                     # mouse_vel_std
        safe_max(velocities),                     # mouse_vel_max
        safe_mean(accelerations),                 # mouse_accel_mean
        safe_std(accelerations),                  # mouse_accel_std
        safe_mean(curvatures),                    # curvature_mean
        safe_std(curvatures),                     # curvature_std
        round(idle_ratio, 4),                     # idle_ratio
        float(len(clicks)),                        # click_count
        safe_mean(click_intervals),               # click_interval_mean
        safe_std(click_intervals),                # click_interval_std
        round(float(session_duration), 2),        # session_duration_ms
        float(len(events)),                        # total_events
        float(len(scrolls)),                        # scroll_count
        float(pause_count),                          # pause_count
        float(len(mousemove)),                        # mousemove_count
    ], dtype=np.float32)

    # Replace NaN / Inf with sensible defaults
    feat = np.nan_to_num(feat, nan=0.0, posinf=1e6, neginf=0.0)
    return feat
STEPUP_THRESHOLD = 60
HOLD_THRESHOLD   = 70
BLOCK_THRESHOLD  = 80

ISO_WEIGHT = 0.60
AE_WEIGHT  = 0.40


def score_isolation_forest(feat_scaled: np.ndarray) -> float:
  
    raw = ISO_FOREST.decision_function(feat_scaled.reshape(1, -1))[0]
    clamped = float(np.clip(raw, -0.5, 0.5))
    # Map [-0.5, 0.5] → [1.0, 0.0]
    return round(1.0 - (clamped + 0.5) / 1.0, 4)


def score_autoencoder(feat_scaled: np.ndarray) -> float:
 
    x    = feat_scaled.reshape(1, -1).astype(np.float32)
    recon = AUTOENCODER.predict(x, verbose=0)
    mae   = float(np.mean(np.abs(x - recon)))
    # normalise against the threshold: score = mae / (2 * threshold)  capped at 1
    score = min(mae / (2.0 * AE_THRESHOLD), 1.0)
    return round(score, 4)


def combine_scores(iso_score: float, ae_score: float) -> float:
  
    blended = ISO_WEIGHT * iso_score + AE_WEIGHT * ae_score   # in [0, 1]
    scaled  = blended * 99.0 + 1.0                            # → [1, 100]
    return round(scaled, 2)


def decide(risk_score: float, n_events: int) -> str:

    if risk_score > BLOCK_THRESHOLD:
        return "block"
    if risk_score > HOLD_THRESHOLD:
        return "hold"
    if risk_score > STEPUP_THRESHOLD:
        return "stepup"
    return "allow"


#  API ENDPOINT


@app.route("/api/score-session", methods=["POST"])
def score_session():
    data = request.get_json(force=True, silent=True) or {}

    user_id     = data.get("user_id",     "unknown")
    session_id  = data.get("session_id",  "?")
    events      = data.get("events",      [])

    print(f"\n  [{session_id}] user={user_id} events={len(events)}")

    if events:
        sample_keys = sorted(set(events[0].keys()))
        type_counts = {}
        for e in events:
            t = e.get("type", "<missing>")
            type_counts[t] = type_counts.get(t, 0) + 1
        print(f"  [debug] sample_event_keys={sample_keys}  type_counts={type_counts}")
    else:
        print("  [debug] events list is EMPTY")

    # ── Feature extraction ────────────────────────────────────────────────
    feat_raw    = extract_features(events)
    feat_scaled = SCALER.transform(feat_raw.reshape(1, -1))

    print(f"  [debug] feat_raw={np.round(feat_raw, 2).tolist()}")

    # ── Model scoring ─────────────────────────────────────────────────────
    iso_score = score_isolation_forest(feat_scaled)
    ae_score  = score_autoencoder(feat_scaled)

    risk_score = combine_scores(iso_score, ae_score)
    decision   = decide(risk_score, len(events))

    factors = {
        "isolation_forest": iso_score,
        "autoencoder":      ae_score,
        "combined":         risk_score,
        "event_count":      len(events),
    }

    print(f"  → iso={iso_score:.3f} ae={ae_score:.3f}"
          f"  risk={risk_score:.3f}  decision={decision}")

    return jsonify({
        "risk_score": risk_score,
        "decision":   decision,
        "factors":    factors
    })


@app.route("/health", methods=["GET"])
def health():
    return jsonify({
        "status":         "ok",
        "models_loaded":  True,
        "ae_threshold":   AE_THRESHOLD,
    })


# ── Main ──────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    print()
    print("=" * 52)
    print("  BehaviorGuard AI — Risk Scoring Engine")
    print("=" * 52)
    print("  URL          : http://localhost:8000")
    print(f"  AE threshold : {AE_THRESHOLD:.5f}")
    print("  Models       : Isolation Forest + Autoencoder")
    print()
    print("  Start the web app next:")
    print("  cd ../behaviorguard_web_app && python app.py")
    print("=" * 52)
    print()
    app.run(debug=False, port=8000)
s