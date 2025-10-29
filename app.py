# app.py (Integrated with the ML Wait Time Model)
from flask import Flask, render_template
from flask_socketio import SocketIO, emit
import logging
from datetime import datetime, timezone, timedelta
from notifications import send_email

# --- CORRECTED: Import functions from your ml_model.py file ---
from ml_model import initialize_wait_model, predict_wait_time, refresh_wait_model

# --- Basic Setup ---
app = Flask(__name__)
app.config['SECRET_KEY'] = 'a-truly-secret-key-that-is-safe' 
socketio = SocketIO(app, cors_allowed_origins="*")
logging.basicConfig(level=logging.INFO)

# --- In-Memory Data Store ---
QUEUE = []
NOW_SERVING = None
ADMIN_ID = "admin"
ADMIN_PASSWORD = "password"

# --- NEW: Data store for model training ---
WAIT_LOG = [] # Stores actual wait times to feed back to the model
SERVED_COUNT_FOR_RETRAIN = 0 # Counter to trigger retraining

# --- Helper Function (MODIFIED to use the ML model) ---
def get_queue_details_for_frontend():
    detailed_queue = []
    for i, user_data in enumerate(QUEUE):
        details = user_data.copy()
        join_time_obj = details.get('timestamp')
        
        position = i + 1
        # --- MODIFICATION: Use the ML model for prediction ---
        predicted_wait_minutes = predict_wait_time(position)
        # --- End of modification ---

        details['wait_time'] = round(predicted_wait_minutes, 1)

        if join_time_obj:
            details['join_time'] = join_time_obj.isoformat()
            serve_by_time_obj = join_time_obj + timedelta(minutes=predicted_wait_minutes)
            details['serve_by'] = serve_by_time_obj.astimezone(timezone(timedelta(hours=5, minutes=30))).strftime('%I:%M %p')
        else:
            details['join_time'] = None
            details['serve_by'] = '--'
            
        if 'timestamp' in details:
            del details['timestamp']
            
        detailed_queue.append(details)
        
    return detailed_queue

# --- HTTP Route ---
@app.route('/')
def index():
    return render_template('index.html')

# --- Socket.IO Event Handlers ---

@socketio.on('connect')
def handle_connect():
    logging.info(f"✅ Client connected. Serving queue data.")
    emit('queue_data', {'queue': get_queue_details_for_frontend()})
    emit('now_serving', {'user_id': NOW_SERVING})

@socketio.on('disconnect')
def handle_disconnect():
    logging.info("❌ Client disconnected")

@socketio.on('join_queue')
def handle_join_queue(data):
    user_id = data.get('user_id')
    user_email = data.get('email')
    logging.info(f"👋 Join request received for user: {user_id}")
    
    join_time_obj = datetime.now(timezone.utc)
    new_user = {
        'user_id': user_id,
        'user_name': user_id,
        'email': user_email,
        'timestamp': join_time_obj
    }
    QUEUE.append(new_user)
    
    position = len(QUEUE)
    # --- MODIFICATION: Use ML model for email prediction ---
    estimated_wait = predict_wait_time(position)
    # --- End of modification ---

    if user_email:
        serve_by_time_obj = join_time_obj + timedelta(minutes=estimated_wait)
        serve_by_time_str = serve_by_time_obj.astimezone(timezone(timedelta(hours=5, minutes=30))).strftime('%I:%M %p')

        subject = "Queue Confirmation"
        body = (f"Hi {user_id},\n\n"
                f"You have successfully joined the queue.\n\n"
                f"Your position: {position}\n"
                f"Estimated wait time: {estimated_wait:.1f} minutes\n"
                f"Expected to be served by: {serve_by_time_str} (IST)")
        send_email(user_email, subject, body)

    emit('position_updated', {'user_id': user_id, 'position': position, 'estimated_wait': estimated_wait})
    socketio.emit('queue_data', {'queue': get_queue_details_for_frontend()})
    logging.info(f"➡️ Queue updated. New size: {len(QUEUE)}")

@socketio.on('next_user')
def handle_next_user():
    global NOW_SERVING, SERVED_COUNT_FOR_RETRAIN
    if QUEUE:
        served_user = QUEUE.pop(0)
        NOW_SERVING = served_user.get('user_name')
        logging.info(f"🔔 Now serving: {NOW_SERVING}")

        # --- NEW: Log actual wait time for the served user ---
        time_joined = served_user.get('timestamp')
        if time_joined:
            time_served = datetime.now(timezone.utc)
            actual_wait_duration_seconds = (time_served - time_joined).total_seconds()
            WAIT_LOG.append({'duration': actual_wait_duration_seconds})
            logging.info(f"📊 Logged actual wait time for {NOW_SERVING}: {actual_wait_duration_seconds:.2f} seconds.")
            
            # --- NEW: Trigger model retraining every 5 users ---
            SERVED_COUNT_FOR_RETRAIN += 1
            if SERVED_COUNT_FOR_RETRAIN >= 5:
                logging.info("🔄 Reached 5 served users. Triggering model retraining...")
                refresh_wait_model(WAIT_LOG)
                SERVED_COUNT_FOR_RETRAIN = 0 # Reset counter
        # --- End of new logic ---

        if len(QUEUE) >= 3:
            user_at_pos_3 = QUEUE[2]
            recipient_name = user_at_pos_3.get('user_name')
            recipient_email = user_at_pos_3.get('email')
            
            if recipient_email:
                estimated_remaining_wait = predict_wait_time(3) # Predict for position 3
                serve_by_time_obj = datetime.now(timezone.utc) + timedelta(minutes=estimated_remaining_wait)
                serve_by_time_str = serve_by_time_obj.astimezone(timezone(timedelta(hours=5, minutes=30))).strftime('%I:%M %p')

                subject = "You're Getting Close!"
                body = (f"Hi {recipient_name},\n\n"
                        f"You are now 3rd in the queue!\n\n"
                        f"Estimated remaining wait time: {estimated_remaining_wait:.1f} minutes\n"
                        f"You should be served by approximately: {serve_by_time_str} (IST)")
                send_email(recipient_email, subject, body)
    else:
        NOW_SERVING = None
        logging.info("🔔 Queue is empty.")
    socketio.emit('now_serving', {'user_id': NOW_SERVING})
    socketio.emit('queue_data', {'queue': get_queue_details_for_frontend()})

@socketio.on('clear_queue')
def handle_clear_queue():
    global QUEUE, NOW_SERVING
    QUEUE.clear()
    NOW_SERVING = None
    logging.info("🗑️ Queue has been cleared.")
    socketio.emit('now_serving', {'user_id': NOW_SERVING})
    socketio.emit('queue_data', {'queue': get_queue_details_for_frontend()})

@socketio.on('admin_login')
def handle_admin_login(data):
    if data.get('user_id') == ADMIN_ID and data.get('password') == ADMIN_PASSWORD:
        logging.info("✅ Admin login successful.")
        emit('login_success')
    else:
        logging.warning("❌ Admin login failed.")
        emit('login_failed')

@socketio.on('get_queue')
def handle_get_queue():
    emit('queue_data', {'queue': get_queue_details_for_frontend()})

# --- Main Execution ---
if __name__ == '__main__':
    # --- NEW: Initialize the model on startup ---
    initialize_wait_model()
    logging.info("🚀 Starting SmartQueue Standalone Server...")
    socketio.run(app, debug=True, allow_unsafe_werkzeug=True)
