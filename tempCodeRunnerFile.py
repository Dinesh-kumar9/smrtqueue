# app.py (FINAL VERSION)
from flask import Flask, render_template
from flask_socketio import SocketIO, emit
import logging
from config import ADMIN_ID, ADMIN_PASSWORD
from ml_model import initialize_wait_model, refresh_wait_model, predict_wait_time
# We now go back to using the proper queue_logic file
from queue_logic import (
    add_to_queue, get_position, serve_next_user,
    clear_queue, get_waiting_queue, wait_log
)

app = Flask(__name__)
socketio = SocketIO(app)
logging.basicConfig(level=logging.INFO)

@app.route('/')
def index():
    return render_template('index.html')

# --- All event handlers are now restored to their final versions ---

@socketio.on('admin_login')
def handle_admin_login(data):
    if data.get('user_id') == ADMIN_ID and data.get('password') == ADMIN_PASSWORD:
        emit('login_success')
    else:
        emit('login_failed')

@socketio.on('join_queue')
def handle_join(data):
    user_id, email = data.get('user_id'), data.get('email')
    add_to_queue(user_id, email=email, user_name=user_id)
    position = get_position(user_id)
    est_time = predict_wait_time(position)
    emit('position_updated', {'user_id': user_id, 'position': position or -1, 'estimated_wait': round(est_time, 2)}, broadcast=True)
    emit('queue_data', {'queue': get_waiting_queue()}, broadcast=True)

@socketio.on('next_user')
def handle_next():
    served_user, wait_time = serve_next_user()
    if served_user:
        wait_log.append({'position': len(get_waiting_queue()) + 1, 'duration': wait_time})
        if len(wait_log) >= 2:
            refresh_wait_model(wait_log)
    emit('now_serving', {'user_id': served_user, 'wait_time': round(wait_time / 60, 2)}, broadcast=True)
    emit('queue_data', {'queue': get_waiting_queue()}, broadcast=True)

@socketio.on('clear_queue')
def handle_clear():
    clear_queue()
    emit('queue_data', {'queue': []}, broadcast=True)
    emit('now_serving', {'user_id': None, 'wait_time': 0}, broadcast=True)

@socketio.on('get_queue')
def handle_get_queue():
    emit('queue_data', {'queue': get_waiting_queue()})

if __name__ == '__main__':
    logging.info("🚀 Starting SmartQueue Server...")
    initialize_wait_model()
    socketio.run(app, debug=True)