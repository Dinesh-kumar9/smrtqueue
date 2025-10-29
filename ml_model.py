from sklearn.linear_model import LinearRegression
import numpy as np
import joblib
import logging
import os

# 🧠 Global model reference
wait_time_model = None
MODEL_PATH = "wait_time_model.pkl"  # Saves and loads from root folder

# 📝 Set up logging
logging.basicConfig(level=logging.INFO)

# 📄 Prepare training data from wait logs
def prepare_training_data_from_log(wait_log):
    data = []
    for i, log in enumerate(wait_log):
        if "duration" in log:
            data.append({
                "position": i + 1,
                "wait_time": log["duration"]
            })
        else:
            logging.warning(f"Missing 'duration' in log entry {i}")
    return data

# 🚀 Train model using prepared data
def train_wait_model(wait_log):
    data = prepare_training_data_from_log(wait_log)
    if len(data) < 2:
        logging.warning("Not enough data to train wait time model.")
        return None

    X = np.array([entry['position'] for entry in data]).reshape(-1, 1)
    y = np.array([entry['wait_time'] for entry in data])

    model = LinearRegression()
    model.fit(X, y)
    logging.info(f"✅ Model trained on {len(data)} entries.")
    return model

# 💾 Save model to disk
def save_wait_model(model, path=MODEL_PATH):
    try:
        joblib.dump(model, path)
        logging.info(f"📁 Model saved at '{path}'")
    except Exception as e:
        logging.error(f"❌ Save failed: {e}")

# 📂 Load model from disk
def load_wait_model(path=MODEL_PATH):
    if os.path.exists(path):
        try:
            model = joblib.load(path)
            logging.info(f"📂 Model loaded from '{path}'")
            return model
        except Exception as e:
            logging.error(f"❌ Load failed: {e}")
            return None
    else:
        logging.warning(f"⚠️ No model found at '{path}'")
        return None

# 🔁 Train and update global model
def refresh_wait_model(wait_log):
    global wait_time_model
    wait_time_model = train_wait_model(wait_log)
    if wait_time_model:
        save_wait_model(wait_time_model)
    return wait_time_model

# 🚦 Load saved model (call at startup)
def initialize_wait_model():
    global wait_time_model
    wait_time_model = load_wait_model()

# 🔮 Predict wait time from queue position
def predict_wait_time(current_position):
    global wait_time_model
    if wait_time_model:
        try:
            prediction = float(wait_time_model.predict([[current_position]])[0])
            logging.info(f"🔮 Prediction for position {current_position}: {prediction:.2f} seconds")
            return round(prediction / 60, 2)  # Convert to minutes
        except Exception as e:
            logging.error(f"❌ Prediction error: {e}")
            return 4.0  # Fallback
    else:
        logging.warning("⚠️ No model available. Using fallback wait time.")
        return 4.0