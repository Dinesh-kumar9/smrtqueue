# ml_model.py — Enhanced Multi-Feature Wait Time Model
from sklearn.linear_model import LinearRegression
import numpy as np
import joblib
import logging
import os
from collections import deque
from datetime import datetime

logging.basicConfig(level=logging.INFO)

# ── Global State ────────────────────────────────────────────────────────────
import tempfile

# ── Global State ────────────────────────────────────────────────────────────
wait_time_model = None
# Vercel only allows writing to /tmp
MODEL_PATH = os.path.join(tempfile.gettempdir(), "wait_time_model.pkl")

# Rolling window of recent actual wait times (in seconds) for smart fallback
_recent_waits = deque(maxlen=20)


# ── Feature Engineering ─────────────────────────────────────────────────────
def _build_features(position: int, queue_length: int = None, hour: int = None):
    """Build a feature vector: [position, queue_length, hour_of_day]"""
    if queue_length is None:
        queue_length = position  # conservative estimate
    if hour is None:
        hour = datetime.now().hour
    return [[position, queue_length, hour]]


# ── Fallback Wait Time ───────────────────────────────────────────────────────
MIN_WAIT_PER_PERSON = 2.0   # minimum assumed wait per person (minutes)

def _fallback_wait(position: int) -> float:
    """
    Smart fallback: use rolling average of actual per-person wait times.
    Falls back to MIN_WAIT_PER_PERSON if no history yet.
    """
    if _recent_waits:
        # Each entry is the total wait for one person in seconds.
        # Average seconds per person → convert to minutes → multiply by position.
        avg_seconds_per_person = sum(_recent_waits) / len(_recent_waits)
        avg_minutes_per_person = max(MIN_WAIT_PER_PERSON, avg_seconds_per_person / 60)
        return round(avg_minutes_per_person * position, 2)
    return MIN_WAIT_PER_PERSON * position  # 2 min per person default


# ── Training Data Preparation ────────────────────────────────────────────────
def prepare_training_data_from_log(wait_log):
    data = []
    for i, log in enumerate(wait_log):
        if "duration" in log:
            hour = log.get("hour", datetime.now().hour)
            queue_len = log.get("queue_length", i + 1)
            data.append({
                "position": i + 1,
                "queue_length": queue_len,
                "hour": hour,
                "wait_time": log["duration"]
            })
        else:
            logging.warning(f"Missing 'duration' in log entry {i}")
    return data


# ── Train ────────────────────────────────────────────────────────────────────
def train_wait_model(wait_log):
    data = prepare_training_data_from_log(wait_log)
    if len(data) < 2:
        logging.warning("Not enough data to train wait time model.")
        return None

    X = np.array([[d['position'], d['queue_length'], d['hour']] for d in data])
    y = np.array([d['wait_time'] for d in data])

    model = LinearRegression()
    model.fit(X, y)
    logging.info(f"✅ Model trained on {len(data)} entries (multi-feature).")
    return model


# ── Save / Load ──────────────────────────────────────────────────────────────
def save_wait_model(model, path=MODEL_PATH):
    try:
        joblib.dump(model, path)
        logging.info(f"📁 Model saved at '{path}'")
    except Exception as e:
        logging.error(f"❌ Save failed: {e}")


def load_wait_model(path=MODEL_PATH):
    if os.path.exists(path):
        try:
            model = joblib.load(path)
            # ── Version guard: ensure model expects exactly 3 features ──
            expected_features = 3
            actual_features = getattr(model, 'n_features_in_', None)
            if actual_features != expected_features:
                logging.warning(
                    f"⚠️ Stale model detected ({actual_features} features, need {expected_features}). "
                    f"Deleting '{path}' and starting fresh."
                )
                os.remove(path)
                return None
            logging.info(f"📂 Model loaded from '{path}' ({actual_features} features ✅)")
            return model
        except Exception as e:
            logging.error(f"❌ Load failed: {e}")
    return None


# ── Public API ───────────────────────────────────────────────────────────────
def initialize_wait_model():
    global wait_time_model
    wait_time_model = load_wait_model()
    if not wait_time_model:
        logging.warning("⚠️ No saved model found. Using smart fallback until enough data is collected.")


def refresh_wait_model(wait_log):
    global wait_time_model
    wait_time_model = train_wait_model(wait_log)
    if wait_time_model:
        save_wait_model(wait_time_model)
    return wait_time_model


def log_actual_wait(duration_seconds: float, queue_length: int = 1):
    """Call this every time a user is served to update the rolling fallback."""
    _recent_waits.append(duration_seconds)
    logging.info(f"📊 Logged actual wait: {duration_seconds:.1f}s | Rolling avg: {sum(_recent_waits)/len(_recent_waits):.1f}s")


def predict_wait_time(position: int, queue_length: int = None) -> float:
    """Returns predicted wait time in minutes for a given queue position."""
    global wait_time_model
    hour = datetime.now().hour
    if queue_length is None:
        queue_length = position

    if wait_time_model:
        try:
            features = _build_features(position, queue_length, hour)
            prediction = float(wait_time_model.predict(features)[0])
            prediction = max(0.5, prediction)  # never predict negative
            logging.info(f"🔮 ML prediction for pos {position}: {prediction:.1f}s → {prediction/60:.2f} min")
            return round(prediction / 60, 2)
        except Exception as e:
            logging.error(f"❌ Prediction error: {e}")

    # Smart fallback
    fb = _fallback_wait(position)
    logging.warning(f"⚠️ Using fallback wait: {fb:.2f} min for position {position}")
    return fb