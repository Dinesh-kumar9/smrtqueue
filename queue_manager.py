# queue_manager.py
import time
from notifications import send_email

# --- Configuration ---
# Notify users when they reach this position in the queue.
NOTIFICATION_THRESHOLD = 3 

# This list will act as our queue
user_queue = []

def add_user_to_queue(name, email):
    """Adds a user to the queue and sends an initial confirmation email."""
    print(f"Adding {name} to the queue...")
    
    position = len(user_queue) + 1
    user_queue.append({'name': name, 'email': email})
    
    print(f"✅ {name} has been added to the queue at position {position}.")

    # Send initial confirmation email
    subject = "You're in the Queue!"
    body = (
        f"Hi {name},\n\n"
        f"This is a confirmation that you've been successfully added to the queue. "
        f"Your current position is #{position}.\n\n"
        f"We'll notify you again when you're near the front."
    )
    send_email(to_email=email, subject=subject, body=body)

def process_next_user():
    """Processes the user at the front of the queue and notifies others who are now close."""
    if not user_queue:
        print("📭 The queue is empty. No one to process.")
        return

    # Remove the user from the front of the queue
    processed_user = user_queue.pop(0)
    print(f"\n✅ Processing user: {processed_user['name']}. They are now out of the queue.")
    print("Positions have been updated for remaining users.")

    # --- Check and Notify Users Nearing the Front ---
    for i, user in enumerate(user_queue):
        current_position = i + 1
        if current_position == NOTIFICATION_THRESHOLD:
            print(f"🔔 User {user['name']} has reached position #{current_position}. Triggering 'almost your turn' notification.")
            
            # Send the "your turn is near" email
            subject = "Your turn is coming up soon!"
            body = (
                f"Hi {user['name']},\n\n"
                f"Get ready! You are now at position #{current_position} in the queue. "
                f"Your turn is coming up very soon.\n\n"
                f"Thanks for your patience!"
            )
            send_email(to_email=user['email'], subject=subject, body=body)

# --- Example of how to run the system ---
if __name__ == "__main__":
    print("🚀 Queue Management System is active.")
    print(f"Users will be notified when they reach position: {NOTIFICATION_THRESHOLD}")
    print("-" * 30)

    # 1. Add users to the queue
    add_user_to_queue("Alice", "alice_test@example.com")
    add_user_to_queue("Bob", "bob_test@example.com")
    add_user_to_queue("Charlie", "charlie_test@example.com")
    add_user_to_queue("Diana", "diana_test@example.com")

    # 2. Process users from the front, which triggers notifications for others
    time.sleep(2) # Pausing for dramatic effect
    process_next_user() # Processes Alice. Charlie moves to position 3 and gets an email.
    
    time.sleep(2)
    process_next_user() # Processes Bob. Diana moves to position 3 and gets an email.