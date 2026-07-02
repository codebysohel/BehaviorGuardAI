from flask import (Flask, render_template, request, redirect,
                   url_for, session, flash, jsonify)
from flask_cors import CORS
import requests, json
from datetime import datetime

import database as db

app = Flask(__name__)
app.secret_key  = "behaviorguard-secret-change-in-production"
CORS(app)

RISK_API_URL    = "http://localhost:8000/api/score-session"
DEMO_OTP        = "123456"

# ── Risk thresholds (no trust phases — simple fixed thresholds) ───────────────
ALLOW_MAX  = 45    # 0–30  → allow
OTP_MAX    = 60    # 31–60 → OTP step-up
                   # 61+   → block


# ── Call Risk API ─────────────────────────────────────────────────────────────

def call_risk_api(user, events):
    
    try:
        payload = {
            "user_id":     user["username"],
            "session_id":  f"web-{datetime.now().timestamp()}",
            "platform":    "web",
            "trust_phase": 4,    # always use full scoring — no trust phases
            "events":      events
        }
        resp = requests.post(RISK_API_URL, json=payload, timeout=5)
        if resp.status_code == 200:
            data = resp.json()
            # Apply our own thresholds (override the API's trust-phase logic)
            score    = data["risk_score"]
            decision = decide(score)
            return score, decision, data.get("factors", {}), data.get("latency_ms", 0)
    except Exception as e:
        print(f"  Risk API offline: {e}")

    return -1, "allow", {"note": "Risk API offline — defaulting to allow"}, 0


def decide(score: int) -> str:
    if score < 0:        return "allow"   # API offline
    if score <= ALLOW_MAX: return "allow"
    if score <= OTP_MAX:   return "otp"
    return "block"


@app.route("/", methods=["GET"])
def index():
    if "user_id" in session:
        return redirect(url_for("home"))
    return render_template("login.html")


@app.route("/login", methods=["POST"])
def login():
    username = request.form.get("username", "").strip()
    password = request.form.get("password", "").strip()
    events   = json.loads(request.form.get("events", "[]"))

    # ── Step 1: Check user exists and password is correct ─────────────────
    user = db.authenticate(username, password)

    if not user:
        # Check if username exists to give a helpful message
        exists = db.get_user_by_username(username)
        if not exists:
            flash("Username not found. Please check your username or register.", "error")
        else:
            flash("Incorrect password. Please try again.", "error")
        return redirect(url_for("index"))

    # ── Step 2: Call Risk API with behavioral events ──────────────────────
    risk_score, decision, factors, latency_ms = call_risk_api(user, events)

    # ── Step 3: Log everything to MySQL (visible in phpMyAdmin) ──────────
    db.log_session(
        user_id    = user["id"],
        event_count= len(events),
        risk_score = risk_score,
        decision   = decision,
        ip_address = request.remote_addr,
        latency_ms = latency_ms
    )

    # ── Step 4: Route based on decision ──────────────────────────────────
    if decision == "block":
        return render_template("blocked.html",
            username   = user["username"],
            risk_score = risk_score,
            factors    = factors
        )

    if decision == "otp":
        session["pending_user_id"]    = user["id"]
        session["pending_username"]   = user["username"]
        session["pending_risk_score"] = risk_score
        session["pending_factors"]    = factors
        return render_template("otp.html",
            risk_score = risk_score,
            factors    = factors
        )

    # allow — grant access
    _grant_access(user, risk_score, factors, latency_ms)
    return redirect(url_for("home"))


def _grant_access(user, risk_score, factors, latency_ms):
    """Store user info in session to indicate logged-in state."""
    session["user_id"]    = user["id"]
    session["username"]   = user["username"]
    session["risk_score"] = risk_score
    session["factors"]    = factors
    session["latency_ms"] = latency_ms


# ── OTP verification ──────────────────────────────────────────────────────────

@app.route("/verify-otp", methods=["POST"])
def verify_otp():
    entered    = request.form.get("otp", "").strip()
    user_id    = session.get("pending_user_id")
    username   = session.get("pending_username")
    risk_score = session.get("pending_risk_score", -1)
    factors    = session.get("pending_factors", {})

    if not user_id:
        return redirect(url_for("index"))

    if entered == DEMO_OTP:
        # OTP correct — clear pending state and grant access
        for k in ["pending_user_id","pending_username",
                  "pending_risk_score","pending_factors"]:
            session.pop(k, None)
        session["user_id"]    = user_id
        session["username"]   = username
        session["risk_score"] = risk_score
        session["factors"]    = factors
        session["latency_ms"] = 0
        flash("✓ Identity verified successfully.", "success")
        return redirect(url_for("home"))
    else:
        flash("Incorrect OTP. Please try again.", "error")
        return render_template("otp.html",
            risk_score = risk_score,
            factors    = factors
        )


# ── Home ──────────────────────────────────────────────────────────────────────

@app.route("/home")
def home():
    if "user_id" not in session:
        return redirect(url_for("index"))

    risk_score = session.get("risk_score", -1)
    factors    = session.get("factors", {})
    latency_ms = session.get("latency_ms", 0)
    history    = db.get_recent_sessions(session["user_id"], limit=8)

    # Score color for the gauge
    if risk_score < 0:
        color, label = "#1156AE", "No score (API offline)"
    elif risk_score <= ALLOW_MAX:
        color, label = "#007A52", f"Low risk — access granted"
    elif risk_score <= OTP_MAX:
        color, label = "#B45309", f"Medium risk — OTP verified"
    else:
        color, label = "#C0392B", f"High risk"

    return render_template("home.html",
        username   = session["username"],
        risk_score = risk_score,
        color      = color,
        label      = label,
        factors    = factors,
        latency_ms = latency_ms,
        history    = history,
        allow_max  = ALLOW_MAX,
        otp_max    = OTP_MAX
    )


# ── Register ──────────────────────────────────────────────────────────────────

@app.route("/register", methods=["GET","POST"])
def register():
    if request.method == "POST":
        username = request.form.get("username","").strip()
        password = request.form.get("password","").strip()
        confirm  = request.form.get("confirm","").strip()

        if password != confirm:
            flash("Passwords do not match.", "error")
        else:
            ok, msg = db.register_user(username, password)
            if ok:
                flash("Account created! You can now log in.", "success")
                return redirect(url_for("index"))
            else:
                flash(msg, "error")

    return render_template("register.html")


# ── Dashboard ─────────────────────────────────────────────────────────────────

@app.route("/dashboard")
def dashboard():
    if "user_id" not in session:
        return redirect(url_for("index"))
    sessions = db.get_all_sessions(limit=50)
    stats    = db.get_stats()
    return render_template("dashboard.html",
        sessions   = sessions,
        stats      = stats,
        allow_max  = ALLOW_MAX,
        otp_max    = OTP_MAX
    )


@app.route("/api/live-stats")
def live_stats():
    """Called by dashboard JS every 5 seconds for auto-refresh."""
    if "user_id" not in session:
        return jsonify({"error": "not authenticated"}), 401
    sessions = db.get_all_sessions(limit=20)
    stats    = db.get_stats()
    # Convert datetime objects to strings for JSON
    for s in sessions:
        if hasattr(s.get("timestamp"), "isoformat"):
            s["timestamp"] = s["timestamp"].strftime("%Y-%m-%d %H:%M:%S")
    return jsonify({"sessions": sessions, "stats": stats})


# ── Logout ────────────────────────────────────────────────────────────────────

@app.route("/logout")
def logout():
    session.clear()
    flash("You have been logged out.", "info")
    return redirect(url_for("index"))


if __name__ == "__main__":
    print()
    print("=" * 54)
    print("  BehaviorGuard AI — Web App")
    print("=" * 54)
    print("  URL          : http://localhost:5000")
    print("  Dashboard    : http://localhost:5000/dashboard")
    print("  Demo users   : alice / Test@1234")
    print("                 bob   / Test@1234")
    print()
    print("  Risk thresholds:")
    print(f"  0–{ALLOW_MAX}  → ALLOW")
    print(f"  {ALLOW_MAX+1}–{OTP_MAX} → OTP")
    print(f"  {OTP_MAX+1}+    → BLOCK")
    print()
    print("  Risk API: http://localhost:8000")
    print("=" * 54)
    print()
    app.run(debug=True, port=5000)
