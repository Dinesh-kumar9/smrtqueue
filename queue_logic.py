# queue_logic.py (FINAL RECTIFIED VERSION)
import time
from pymongo import MongoClient
from datetime import datetime, timedelta, timezone 
from notifications import send_email
from ml_model import predict_wait_time

NOTIFICATION_THRESHOLD = 3
client = MongoClient("mongodb://localhost:27017/")
db = client.smartqueue
queue_collection = db.queue_entries
wait_log = []

def get_waiting_queue():
    """
    Retrieves the waiting list and adds the CORRECT keys and data 
    that the frontend JavaScript expects.
    """
    waiting_users_cursor = queue_collection.find({"status": "waiting"}).sort("timestamp", 1)
    
    queue_list = []
    for i, user in enumerate(waiting_users_cursor):
        position = i + 1
        
        # --- THIS IS THE CORE FIX ---
        join_time_obj = user["timestamp"]
        
        # 1. Create the 'join_time' key (as a string) that the frontend expects.
        user["join_time"] = join_time_obj.isoformat()
        
        # 2. Calculate the CURRENT wait time and add it as the 'wait_time' key.
        current_wait_seconds = (datetime.utcnow() - join_time_obj).total_seconds()
        user["wait_time"] = round(current_wait_seconds / 60)
        
        # Keep the estimated wait for notifications if needed
        user["estimated_wait"] = predict_wait_time(position)
        
        # Convert MongoDB's ObjectId to a string for JSON compatibility
        user["_id"] = str(user["_id"])
        
        queue_list.append(user)
        
    return queue_list

def _check_and_notify():
    """
    Checks the DB and notifies users who reach the threshold.
    (No changes needed here)
    """
    waiting_users = get_waiting_queue()
    if len(waiting_users) >= NOTIFICATION_THRESHOLD:
        user_to_notify = waiting_users[NOTIFICATION_THRESHOLD - 1]
        
        if not user_to_notify.get("notified"):
            user_name = user_to_notify.get("user_name", "there")
            user_email = user_to_notify.get("email")
            
            estimated_wait_minutes = user_to_notify.get("estimated_wait", 0)
            expected_serve_time = datetime.now() + timedelta(minutes=estimated_wait_minutes)
            expected_serve_time_str = expected_serve_time.strftime('%I:%M %p')
            
            subject = "Your turn is coming up soon!"
            body = (
                f"Hi {user_name},\n\n"
                f"Get ready! You are now at position #{NOTIFICATION_THRESHOLD} in the queue.\n\n"
                f"Your expected serving time is approximately {expected_serve_time_str}."
            )
            
            send_email(user_email, subject, body)
            
            queue_collection.update_one(
                {"user_id": user_to_notify["user_id"], "status": "waiting"},
                {"$set": {"notified": True}}
            )

def add_to_queue(user_id, email=None, user_name=None):
    """
    Adds a user to the DB and sends a confirmation email.
    (No changes needed here)
    """
    if queue_collection.find_one({"user_id": user_id, "status": "waiting"}):
        return
        
    position = queue_collection.count_documents({"status": "waiting"}) + 1
    entry = {
        "user_id": user_id, "user_name": user_name, "email": email,
        "timestamp": datetime.utcnow(), "status": "waiting", "notified": False
    }
    queue_collection.insert_one(entry)

    if email:
        subject = "You're in the Queue!"
        estimated_wait_minutes = predict_wait_time(position)
        expected_serve_time = datetime.now() + timedelta(minutes=estimated_wait_minutes)
        expected_serve_time_str = expected_serve_time.strftime('%I:%M %p')
        body = (
            f"Hi {user_name},\n\n"
            f"You have been successfully added to the queue at position #{position}.\n\n"
            f"Your estimated wait time is {estimated_wait_minutes:.2f} minutes.\n"
            f"Your expected serving time is approximately {expected_serve_time_str}."
        )
        send_email(email, subject, body)

def serve_next_user():
    """
    Serves the next user.
    (No changes needed here)
    """
    user_to_serve = queue_collection.find_one_and_update(
        {"status": "waiting"},
        {"$set": {"status": "served", "served_at": datetime.utcnow()}},
        sort=[("timestamp", 1)]
    )
    if not user_to_serve:
        return None, 0
    wait_duration = (datetime.utcnow() - user_to_serve["timestamp"]).total_seconds()
    user_name = user_to_serve.get("user_name") or user_to_serve.get("user_id")
    
    _check_and_notify() 
    
    return user_name, wait_duration

def get_position(user_id):
    """
    Gets a user's position.
    (No changes needed here)
    """
    waiting_users = get_waiting_queue()
    for i, user in enumerate(waiting_users):
        if user["user_id"] == user_id:
            return i + 1
    return -1

def clear_queue():
    """
    Clears the queue.
    (No changes needed here)
    """
    queue_collection.delete_many({"status": "waiting"})
