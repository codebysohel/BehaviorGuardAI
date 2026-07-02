import hashlib
import mysql.connector
from datetime import datetime

# ── Edit these to match your MySQL setup ─────────────────────────────────────
DB_CONFIG = {
    "host":     "localhost",
    "user":     "root",          # your phpMyAdmin username
    "password": "",              # your phpMyAdmin password (often blank on localhost)
    "database": "behaviorguard1"
}


def get_connection():
    return mysql.connector.connect(**DB_CONFIG)


def hash_password(password: str) -> str:
    return hashlib.sha256(password.encode()).hexdigest()


# ── User operations ───────────────────────────────────────────────────────────

def get_user_by_username(username: str):
    """
    Returns user row dict if found, None if not found.
    Used to check if username exists before checking password.
    """
    conn   = get_connection()
    cursor = conn.cursor(dictionary=True)
    cursor.execute(
        "SELECT id, username, password_hash FROM users WHERE username = %s",
        (username.lower().strip(),)
    )
    user = cursor.fetchone()
    cursor.close()
    conn.close()
    return user


def authenticate(username: str, password: str):
    """
    Step 1: Find user by username.
    Step 2: Compare password hash.
    Returns user dict if both match, None otherwise.
    """
    user = get_user_by_username(username)
    if not user:
        return None   # username does not exist
    if user["password_hash"] != hash_password(password):
        return None   # wrong password
    return user


def register_user(username: str, password: str):
    """
    Returns (True, 'ok') on success.
    Returns (False, 'error message') on failure.
    """
    if not username or not password:
        return False, "Username and password are required."
    if len(password) < 6:
        return False, "Password must be at least 6 characters."

    conn   = get_connection()
    cursor = conn.cursor()
    try:
        cursor.execute(
            "INSERT INTO users (username, password_hash, created_at) VALUES (%s, %s, %s)",
            (username.lower().strip(), hash_password(password), datetime.now())
        )
        conn.commit()
        return True, "Account created successfully."
    except mysql.connector.IntegrityError:
        return False, "Username already exists."
    finally:
        cursor.close()
        conn.close()


# ── Session logging ───────────────────────────────────────────────────────────

def log_session(user_id: int, event_count: int,
                risk_score: float, decision: str,
                ip_address: str = "", latency_ms: float = 0):
    """Log every login attempt to login_sessions for phpMyAdmin viewing."""
    conn   = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        """INSERT INTO login_sessions
           (user_id, timestamp, event_count, risk_score, decision, ip_address, latency_ms)
           VALUES (%s, %s, %s, %s, %s, %s, %s)""",
        (user_id, datetime.now(), event_count,
         risk_score, decision, ip_address, latency_ms)
    )
    conn.commit()
    cursor.close()
    conn.close()


def get_recent_sessions(user_id: int, limit: int = 10):
    """Recent login history for one user — shown on home screen."""
    conn   = get_connection()
    cursor = conn.cursor(dictionary=True)
    cursor.execute(
        """SELECT timestamp, risk_score, decision, event_count, latency_ms
           FROM login_sessions WHERE user_id = %s
           ORDER BY timestamp DESC LIMIT %s""",
        (user_id, limit)
    )
    rows = cursor.fetchall()
    cursor.close()
    conn.close()
    return rows


def get_all_sessions(limit: int = 50):
    """All sessions across all users — for the dashboard."""
    conn   = get_connection()
    cursor = conn.cursor(dictionary=True)
    cursor.execute(
        """SELECT ls.timestamp, u.username, ls.risk_score,
                  ls.decision, ls.event_count, ls.latency_ms
           FROM login_sessions ls
           JOIN users u ON ls.user_id = u.id
           ORDER BY ls.timestamp DESC LIMIT %s""",
        (limit,)
    )
    rows = cursor.fetchall()
    cursor.close()
    conn.close()
    return rows


def get_stats():
    """Summary counts for the dashboard."""
    conn   = get_connection()
    cursor = conn.cursor(dictionary=True)
    cursor.execute("""
        SELECT
          COUNT(*) as total,
          SUM(decision = 'allow')  as allowed,
          SUM(decision = 'otp')    as otp,
          SUM(decision = 'block')  as blocked,
          AVG(NULLIF(risk_score,-1)) as avg_score
        FROM login_sessions
    """)
    stats = cursor.fetchone()
    cursor.close()
    conn.close()
    return stats or {}
