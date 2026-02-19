# app.py — SmartQueue with Supabase Persistence
from flask import Flask, render_template
from flask_socketio import SocketIO, emit
import logging
import threading
from datetime import datetime, timezone, timedelta
from supabase import create_client, Client
from notifications import send_email_html
from config import ADMIN_ID, ADMIN_PASSWORD, SUPABASE_URL, SUPABASE_KEY

from ml_model import (
    initialize_wait_model, predict_wait_time,
    refresh_wait_model, log_actual_wait
)

# ── Basic Setup ──────────────────────────────────────────────────────────────
app = Flask(__name__)
app.config['SECRET_KEY'] = 'a-truly-secret-key-that-is-safe'
socketio = SocketIO(app, cors_allowed_origins="*")
logging.basicConfig(level=logging.INFO)

IST = timezone(timedelta(hours=5, minutes=30))

# ── Supabase Client ──────────────────────────────────────────────────────────
sb: Client = create_client(SUPABASE_URL, SUPABASE_KEY)
TABLE = "queue_entries"

# ── Runtime State (non-persistent) ──────────────────────────────────────────
QUEUE_PAUSED = False
NOW_SERVING  = None

# ML retraining
WAIT_LOG = []
SERVED_COUNT_FOR_RETRAIN = 0
RETRAIN_EVERY = 3

# Priority order
PRIORITY_ORDER = {"emergency": 0, "senior": 1, "normal": 2}


# ── Supabase Helpers ─────────────────────────────────────────────────────────
def db_get_waiting_queue():
    """Fetch all waiting users sorted by priority then join time."""
    try:
        res = sb.table(TABLE).select("*").eq("status", "waiting").order("joined_at").execute()
        rows = res.data or []
        # Sort by priority then joined_at (Supabase can't sort by custom order natively)
        rows.sort(key=lambda u: (PRIORITY_ORDER.get(u.get("priority", "normal"), 2), u["joined_at"]))
        return rows
    except Exception as e:
        logging.error(f"❌ db_get_waiting_queue: {e}")
        return []


def db_add_user(user_id, email, priority, user_name):
    try:
        sb.table(TABLE).insert({
            "user_id":   user_id,
            "user_name": user_name,
            "email":     email,
            "priority":  priority,
            "status":    "waiting",
            "notified":  False,
        }).execute()
        return True
    except Exception as e:
        logging.error(f"❌ db_add_user: {e}")
        return False


def db_serve_next():
    """Mark the first waiting user as served. Returns the served row or None."""
    queue = db_get_waiting_queue()
    if not queue:
        return None
    first = queue[0]
    try:
        sb.table(TABLE).update({
            "status":    "served",
            "served_at": datetime.now(timezone.utc).isoformat(),
        }).eq("id", first["id"]).execute()
        return first
    except Exception as e:
        logging.error(f"❌ db_serve_next: {e}")
        return None


def db_remove_user(user_id):
    try:
        sb.table(TABLE).delete().eq("user_id", user_id).eq("status", "waiting").execute()
    except Exception as e:
        logging.error(f"❌ db_remove_user: {e}")


def db_clear_queue():
    try:
        sb.table(TABLE).delete().eq("status", "waiting").execute()
    except Exception as e:
        logging.error(f"❌ db_clear_queue: {e}")


def db_mark_notified(row_id):
    try:
        sb.table(TABLE).update({"notified": True}).eq("id", row_id).execute()
    except Exception as e:
        logging.error(f"❌ db_mark_notified: {e}")


def db_get_stats():
    """Returns served_today count and avg wait in minutes (or None if no data)."""
    try:
        today_start = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0).isoformat()
        res = sb.table(TABLE).select("joined_at,served_at").eq("status", "served").gte("served_at", today_start).execute()
        rows = res.data or []
        served_today = len(rows)
        waits = []
        for r in rows:
            if r.get("joined_at") and r.get("served_at"):
                try:
                    j = datetime.fromisoformat(r["joined_at"].replace("Z", "+00:00"))
                    s = datetime.fromisoformat(r["served_at"].replace("Z", "+00:00"))
                    diff = (s - j).total_seconds()
                    if diff > 0:  # guard against clock skew / negative values
                        waits.append(diff)
                except Exception:
                    pass
        # Return None when no valid data — frontend will show '--'
        avg_wait = round(sum(waits) / len(waits) / 60, 1) if waits else None
        return served_today, avg_wait
    except Exception as e:
        logging.error(f"❌ db_get_stats: {e}")
        return 0, None


def db_is_duplicate(user_id):
    try:
        res = sb.table(TABLE).select("id").eq("user_id", user_id).eq("status", "waiting").execute()
        return len(res.data) > 0
    except Exception as e:
        logging.error(f"❌ db_is_duplicate: {e}")
        return False


# ── Frontend Data Builder ────────────────────────────────────────────────────
def get_queue_details_for_frontend():
    queue = db_get_waiting_queue()
    queue_len = len(queue)
    detailed = []
    for i, user in enumerate(queue):
        position = i + 1
        predicted_wait = predict_wait_time(position, queue_len)
        join_time_str = user.get("joined_at", "")
        serve_by = "--"
        if join_time_str:
            try:
                join_dt = datetime.fromisoformat(join_time_str.replace("Z", "+00:00"))
                serve_by = (join_dt + timedelta(minutes=predicted_wait)).astimezone(IST).strftime('%I:%M %p')
            except Exception:
                pass
        detailed.append({
            "user_id":   user.get("user_id"),
            "user_name": user.get("user_name") or user.get("user_id"),
            "email":     user.get("email", ""),
            "priority":  user.get("priority", "normal"),
            "join_time": join_time_str,
            "wait_time": round(predicted_wait, 1),
            "serve_by":  serve_by,
        })
    return detailed


def get_stats():
    served_today, avg_wait = db_get_stats()
    queue = db_get_waiting_queue()
    return {
        "queue_length":    len(queue),
        "served_today":    served_today,
        "avg_wait_minutes": avg_wait,
        "paused":          QUEUE_PAUSED,
    }


def broadcast_all():
    socketio.emit("queue_data",    {"queue": get_queue_details_for_frontend()})
    socketio.emit("stats_update",  get_stats())
    socketio.emit("now_serving",   {"user_id": NOW_SERVING})


def _send_email_bg(to, subject, body_html):
    threading.Thread(target=send_email_html, args=(to, subject, body_html), daemon=True).start()


# ── HTTP Route ───────────────────────────────────────────────────────────────
@app.route("/")
def index():
    return render_template("index.html")


# ── Socket.IO Events ─────────────────────────────────────────────────────────
@socketio.on("connect")
def handle_connect():
    logging.info("✅ Client connected.")
    emit("queue_data",   {"queue": get_queue_details_for_frontend()})
    emit("now_serving",  {"user_id": NOW_SERVING})
    emit("stats_update", get_stats())


@socketio.on("disconnect")
def handle_disconnect():
    logging.info("❌ Client disconnected.")


@socketio.on("join_queue")
def handle_join_queue(data):
    if QUEUE_PAUSED:
        emit("join_rejected", {"reason": "Queue is currently paused by admin."})
        return

    user_id  = data.get("user_id", "").strip()
    email    = data.get("email", "").strip()
    priority = data.get("priority", "normal")

    if not user_id:
        return

    if db_is_duplicate(user_id):
        emit("join_rejected", {"reason": f"'{user_id}' is already in the queue."})
        return

    db_add_user(user_id, email, priority, user_id)

    queue = db_get_waiting_queue()
    position = next((i + 1 for i, u in enumerate(queue) if u["user_id"] == user_id), len(queue))
    estimated_wait = predict_wait_time(position, len(queue))

    logging.info(f"👋 {user_id} joined at position {position} (priority: {priority})")

    if email:
        serve_by = (datetime.now(IST) + timedelta(minutes=estimated_wait)).strftime('%I:%M %p')
        priority_label = priority.capitalize()
        _send_email_bg(email, "✅ Queue Confirmation — SmartQueue", f"""
        <div style="font-family:Inter,sans-serif;max-width:520px;margin:auto;background:#0f0c29;color:#f1f5f9;border-radius:16px;overflow:hidden;">
          <div style="background:linear-gradient(135deg,#7c3aed,#06b6d4);padding:28px 32px;">
            <h2 style="margin:0;font-size:1.5rem;">You're in the Queue! 🎉</h2>
          </div>
          <div style="padding:28px 32px;">
            <p>Hi <strong>{user_id}</strong>,</p>
            <p>You've successfully joined the SmartQueue.</p>
            <table style="width:100%;border-collapse:collapse;margin:20px 0;">
              <tr><td style="padding:10px;color:#a78bfa;font-weight:600;">Position</td><td style="padding:10px;">#{position}</td></tr>
              <tr style="background:rgba(255,255,255,0.05);"><td style="padding:10px;color:#a78bfa;font-weight:600;">Priority</td><td style="padding:10px;">{priority_label}</td></tr>
              <tr><td style="padding:10px;color:#a78bfa;font-weight:600;">Est. Wait</td><td style="padding:10px;">{estimated_wait:.1f} minutes</td></tr>
              <tr style="background:rgba(255,255,255,0.05);"><td style="padding:10px;color:#a78bfa;font-weight:600;">Serve By</td><td style="padding:10px;">{serve_by} IST</td></tr>
            </table>
            <p style="color:#94a3b8;font-size:0.9rem;">You'll receive another email when you're almost at the front.</p>
          </div>
        </div>
        """)

    emit("position_updated", {"user_id": user_id, "position": position, "estimated_wait": estimated_wait, "priority": priority})
    broadcast_all()


@socketio.on("leave_queue")
def handle_leave_queue(data):
    user_id = data.get("user_id", "").strip()
    db_remove_user(user_id)
    logging.info(f"🚪 {user_id} left the queue.")
    emit("left_queue", {"user_id": user_id})
    broadcast_all()


@socketio.on("next_user")
def handle_next_user():
    global NOW_SERVING, SERVED_COUNT_FOR_RETRAIN

    served_user = db_serve_next()
    if not served_user:
        NOW_SERVING = None
        broadcast_all()
        return

    NOW_SERVING = served_user.get("user_name") or served_user.get("user_id")
    logging.info(f"🔔 Now serving: {NOW_SERVING}")

    # Log actual wait for ML
    join_str = served_user.get("joined_at")
    if join_str:
        try:
            join_dt = datetime.fromisoformat(join_str.replace("Z", "+00:00"))
            actual_seconds = (datetime.now(timezone.utc) - join_dt).total_seconds()
            WAIT_LOG.append({"duration": actual_seconds, "queue_length": 1, "hour": datetime.now().hour})
            log_actual_wait(actual_seconds)
            SERVED_COUNT_FOR_RETRAIN += 1
            if SERVED_COUNT_FOR_RETRAIN >= RETRAIN_EVERY:
                threading.Thread(target=refresh_wait_model, args=(WAIT_LOG,), daemon=True).start()
                SERVED_COUNT_FOR_RETRAIN = 0
        except Exception as e:
            logging.error(f"Wait log error: {e}")

    # Notify position-3 user
    queue = db_get_waiting_queue()
    if len(queue) >= 3:
        user_at_3 = queue[2]
        if user_at_3.get("email") and not user_at_3.get("notified"):
            wait3 = predict_wait_time(3, len(queue))
            serve_by = (datetime.now(IST) + timedelta(minutes=wait3)).strftime('%I:%M %p')
            _send_email_bg(user_at_3["email"], "⏰ Almost Your Turn — SmartQueue", f"""
            <div style="font-family:Inter,sans-serif;max-width:520px;margin:auto;background:#0f0c29;color:#f1f5f9;border-radius:16px;overflow:hidden;">
              <div style="background:linear-gradient(135deg,#f59e0b,#ef4444);padding:28px 32px;">
                <h2 style="margin:0;">You're Getting Close! ⚡</h2>
              </div>
              <div style="padding:28px 32px;">
                <p>Hi <strong>{user_at_3.get('user_name', user_at_3['user_id'])}</strong>,</p>
                <p>You are now <strong>#3 in the queue</strong>. Get ready!</p>
                <p>Estimated remaining wait: <strong>{wait3:.1f} minutes</strong></p>
                <p>Expected to be served by: <strong>{serve_by} IST</strong></p>
              </div>
            </div>
            """)
            db_mark_notified(user_at_3["id"])

    # Notify position-1 user ("You're Next!")
    if len(queue) >= 1:
        next_user = queue[0]
        if next_user.get("email"):
            _send_email_bg(next_user["email"], "🚨 You're Next! — SmartQueue", f"""
            <div style="font-family:Inter,sans-serif;max-width:520px;margin:auto;background:#0f0c29;color:#f1f5f9;border-radius:16px;overflow:hidden;">
              <div style="background:linear-gradient(135deg,#10b981,#06b6d4);padding:28px 32px;">
                <h2 style="margin:0;">You're Next! 🎯</h2>
              </div>
              <div style="padding:28px 32px;">
                <p>Hi <strong>{next_user.get('user_name', next_user['user_id'])}</strong>,</p>
                <p>You are now <strong>#1 in the queue</strong>. Please head to the counter!</p>
              </div>
            </div>
            """)
        socketio.emit("you_are_next", {"user_id": next_user["user_id"]})

    broadcast_all()


@socketio.on("clear_queue")
def handle_clear_queue():
    global NOW_SERVING
    db_clear_queue()
    NOW_SERVING = None
    logging.info("🗑️ Queue cleared.")
    broadcast_all()


@socketio.on("pause_queue")
def handle_pause_queue():
    global QUEUE_PAUSED
    QUEUE_PAUSED = True
    logging.info("⏸️ Queue paused.")
    socketio.emit("queue_paused", {})
    socketio.emit("stats_update", get_stats())


@socketio.on("resume_queue")
def handle_resume_queue():
    global QUEUE_PAUSED
    QUEUE_PAUSED = False
    logging.info("▶️ Queue resumed.")
    socketio.emit("queue_resumed", {})
    socketio.emit("stats_update", get_stats())


@socketio.on("admin_login")
def handle_admin_login(data):
    if data.get("user_id") == ADMIN_ID and data.get("password") == ADMIN_PASSWORD:
        logging.info("✅ Admin login successful.")
        emit("login_success")
    else:
        logging.warning("❌ Admin login failed.")
        emit("login_failed")


@socketio.on("get_queue")
def handle_get_queue():
    emit("queue_data",   {"queue": get_queue_details_for_frontend()})
    emit("stats_update", get_stats())


# ── Main ─────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    initialize_wait_model()
    logging.info("🚀 SmartQueue + Supabase starting...")
    socketio.run(app, debug=True, allow_unsafe_werkzeug=True)
