# test_db.py
from pymongo import MongoClient
from pymongo.errors import ConnectionFailure

# --- Configuration ---
MONGO_URI = "mongodb://localhost:27017/"
DB_NAME = "smartqueue"
COLLECTION_NAME = "queue_entries"

def run_test():
    print("--- Starting Database Connection Test ---")
    try:
        # 1. Attempt to connect to the client
        client = MongoClient(MONGO_URI, serverSelectionTimeoutMS=5000)
        # The ismaster command is cheap and does not require auth.
        client.admin.command('ismaster')
        print("✅ Step 1: Successfully connected to MongoDB server.")
        
        # 2. Attempt to connect to the database
        db = client[DB_NAME]
        print(f"✅ Step 2: Successfully connected to database '{DB_NAME}'.")

        # 3. Attempt to find waiting users
        print("--- Querying for users with status: 'waiting' ---")
        waiting_users = list(db[COLLECTION_NAME].find({"status": "waiting"}))
        
        print(f"✅ Step 3: Query finished. Found {len(waiting_users)} user(s).")

        # 4. Print the results
        if waiting_users:
            print("--- Waiting User Details ---")
            for user in waiting_users:
                print(user)
            print("--------------------------")
        
    except ConnectionFailure as e:
        print(f"❌ ERROR: Could not connect to MongoDB.")
        print(f"   Details: {e}")
    except Exception as e:
        print(f"❌ An unexpected error occurred: {e}")
    finally:
        print("--- Test Finished ---")

if __name__ == "__main__":
    run_test()