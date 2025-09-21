from flask import Flask, request, jsonify
from pymongo.mongo_client import MongoClient
from pymongo.server_api import ServerApi
from datetime import datetime
from dotenv import load_dotenv
import os
import traceback

# Load environment variables from .env
load_dotenv()

app = Flask(__name__)

# Build MongoDB URI and connect with explicit TLS & Server API version
MONGO_URI = os.getenv("DATABASE_URL")
if not MONGO_URI:
    raise RuntimeError("Missing DATABASE_URL environment variable")

try:
    client = MongoClient(
        MONGO_URI,
        server_api=ServerApi("1"),
        tls=True,
        tlsAllowInvalidCertificates=False,
        connectTimeoutMS=20000,
        socketTimeoutMS=20000
    )
    db = client["modsplatform"]
    requests_collection = db["requests"]

    # Confirm connectivity at startup
    print("MongoDB client initialized. Connection will be tested via /health.")
except Exception as e:
    print("❌ MongoDB connection error:")
    traceback.print_exc()
    # Let the app continue so /health can report status

# Root route for quick browser check
@app.route("/", methods=["GET"])
def home():
    return "ModsPlatform backend is running!", 200

# Health route to verify DB connectivity without inserting data
@app.route("/health", methods=["GET"])
def health():
    try:
        client.admin.command("ping")
        return jsonify({"status": "ok"}), 200
    except Exception as e:
        return jsonify({"status": "error", "details": str(e)}), 500

# POST /request → Save a new mod request
@app.route("/request", methods=["POST"])
def create_request():
    try:
        data = request.get_json(force=True)
        if not data or not data.get("gameName"):
            return jsonify({"error": "gameName is required"}), 400

        new_request = {
            "gameName": data["gameName"],
            "latestVersion": data.get("latestVersion", ""),
            "details": data.get("details", ""),
            "iconUrl": data.get("iconUrl", ""),
            "timestamp": datetime.utcnow()
        }
        requests_collection.insert_one(new_request)
        return jsonify({"message": "Request submitted successfully"}), 201

    except Exception as e:
        print("❌ Error in /request:")
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500

# GET /requests → Return all stored requests
@app.route("/requests", methods=["GET"])
def get_requests():
    try:
        all_requests = list(requests_collection.find({}, {"_id": 0}))
        return jsonify(all_requests), 200

    except Exception as e:
        print("❌ Error in /requests:")
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500

if __name__ == "__main__":
    # When running locally, print that the server has started
    print("🚀 Starting Flask on http://0.0.0.0:5000")
    app.run(host="0.0.0.0", port=5000)
