from flask import Flask, request, jsonify
from pymongo import MongoClient
from datetime import datetime
import os
from dotenv import load_dotenv

# Load .env variables
load_dotenv()

app = Flask(__name__)

# Connect to MongoDB
client = MongoClient(os.getenv("DATABASE_URL"))
db = client["modsplatform"]
requests_collection = db["requests"]

# POST /request → Save a new request
@app.route("/request", methods=["POST"])
def create_request():
    data = request.json
    if not data.get("gameName"):
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

# GET /requests → Return all requests
@app.route("/requests", methods=["GET"])
def get_requests():
    all_requests = list(requests_collection.find({}, {"_id": 0}))
    return jsonify(all_requests), 200

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)