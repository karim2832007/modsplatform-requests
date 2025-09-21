from flask import Flask, request, jsonify, abort
from pymongo.mongo_client import MongoClient
from pymongo.server_api import ServerApi
from bson import ObjectId
from datetime import datetime
from dotenv import load_dotenv
import os
import traceback
import requests as pyrequests  # for Discord notifications

# Load environment variables from .env
load_dotenv()

app = Flask(__name__)

# Roles
ADMINS    = ["1329817290052734980"]  # Your Discord ID
MANAGERS  = ["850344514605416468"]   # Manager ID

# Discord webhook for notifications
DISCORD_WEBHOOK_URL = os.getenv("DISCORD_WEBHOOK_URL")

def send_discord_notification(message):
    """Send a message to Discord via webhook."""
    if not DISCORD_WEBHOOK_URL:
        return
    try:
        pyrequests.post(DISCORD_WEBHOOK_URL, json={"content": message})
    except Exception as e:
        print("❌ Failed to send Discord notification:", e)

# Build MongoDB URI and connect
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
    print("✅ MongoDB client initialized. Connection will be tested via /health.")
except Exception:
    print("❌ MongoDB connection error:")
    traceback.print_exc()

# Root route
@app.route("/", methods=["GET"])
def home():
    return "ModsPlatform backend is running!", 200

# Health check
@app.route("/health", methods=["GET"])
def health():
    try:
        client.admin.command("ping")
        return jsonify({"status": "ok"}), 200
    except Exception as e:
        return jsonify({"status": "error", "details": str(e)}), 500

# POST /request → Create new request
@app.route("/request", methods=["POST"])
def create_request():
    try:
        data = request.get_json(force=True)
        if not data or not data.get("gameName"):
            return jsonify({"error": "gameName is required"}), 400

        new_request = {
            "gameName":    data["gameName"],
            "latestVersion": data.get("latestVersion", ""),
            "details":       data.get("details", ""),
            "iconUrl":       data.get("iconUrl", ""),
            "createdBy":     data.get("createdBy", "anonymous"),
            "comments":      [],
            "timestamp":     datetime.utcnow(),
            "lastActivity":  datetime.utcnow()
        }
        result = requests_collection.insert_one(new_request)

        # Notify creator, admins, and managers
        notify_ids = set([new_request["createdBy"]] + ADMINS + MANAGERS)
        mention_str = " ".join(f"<@{uid}>" for uid in notify_ids)
        send_discord_notification(
            f"🆕 New request added: **{new_request['gameName']}**\n"
            f"Details: {new_request['details']}\n"
            f"Notifying: {mention_str}"
        )

        return jsonify({
            "message": "Request submitted successfully",
            "id": str(result.inserted_id)
        }), 201

    except Exception as e:
        print("❌ Error in /request:")
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500

# GET /requests → All requests, newest activity first
@app.route("/requests", methods=["GET"])
def get_requests():
    try:
        all_requests = []
        for req in requests_collection.find().sort("lastActivity", -1):
            req["_id"] = str(req["_id"])
            all_requests.append(req)
        return jsonify(all_requests), 200
    except Exception as e:
        print("❌ Error in /requests:")
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500

# GET /request/<id> → Single request details
@app.route("/request/<id>", methods=["GET"])
def get_request(id):
    try:
        req = requests_collection.find_one({"_id": ObjectId(id)})
        if not req:
            return jsonify({"error": "Request not found"}), 404
        req["_id"] = str(req["_id"])
        return jsonify(req), 200
    except Exception as e:
        print("❌ Error in GET /request/<id>:")
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500

# PUT /request/<id> → Edit request (only creator)
@app.route("/request/<id>", methods=["PUT"])
def update_request(id):
    try:
        data = request.get_json(force=True)
        current_user = data.get("currentUserId", "")

        req = requests_collection.find_one({"_id": ObjectId(id)})
        if not req:
            return jsonify({"error": "Request not found"}), 404

        if req.get("createdBy") != current_user:
            return jsonify({"error": "Not authorized to edit this request"}), 403

        update_data = {
            "gameName":     data.get("gameName", req["gameName"]),
            "latestVersion": data.get("latestVersion", req["latestVersion"]),
            "details":       data.get("details", req["details"]),
            "iconUrl":       data.get("iconUrl", req["iconUrl"]),
            "timestamp":     datetime.utcnow(),
            "lastActivity":  datetime.utcnow()
        }

        requests_collection.update_one(
            {"_id": ObjectId(id)},
            {"$set": update_data}
        )
        return jsonify({"message": "Request updated successfully"}), 200

    except Exception as e:
        print("❌ Error in PUT /request/<id>:")
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500

# DELETE /request/<id> → Remove request if creator or admin
@app.route("/request/<id>", methods=["DELETE"])
def delete_request(id):
    try:
        data = request.get_json(force=True)
        current_user = data.get("currentUserId", "")

        req = requests_collection.find_one({"_id": ObjectId(id)})
        if not req:
            return jsonify({"error": "Request not found"}), 404

        if req.get("createdBy") != current_user and current_user not in ADMINS:
            return jsonify({"error": "Not authorized to delete this request"}), 403

        requests_collection.delete_one({"_id": ObjectId(id)})
        return jsonify({"message": "Request deleted successfully"}), 200

    except Exception as e:
        print("❌ Error in DELETE /request/<id>:")
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500

# POST /request/<id>/comment → Add comment (creator, manager, or admin)
@app.route("/request/<id>/comment", methods=["POST"])
def add_comment(id):
    try:
        data = request.get_json(force=True)
        current_user = data.get("currentUserId", "")
        comment_text = data.get("comment", "").strip()

        if not comment_text:
            return jsonify({"error": "Comment cannot be empty"}), 400

        req = requests_collection.find_one({"_id": ObjectId(id)})
        if not req:
            return jsonify({"error": "Request not found"}), 404

        # Allow if creator, manager, or admin
        if (req.get("createdBy") != current_user
                and current_user not in ADMINS
                and current_user not in MANAGERS):
            return jsonify({"error": "Not authorized to comment"}), 403

        comment_entry = {
            "userId":   current_user,
            "comment":  comment_text,
            "timestamp": datetime.utcnow()
        }

        requests_collection.update_one(
            {"_id": ObjectId(id)},
            {
                "$push": {"comments": comment_entry},
                "$set":  {"lastActivity": datetime.utcnow()}
            }
        )

        # Notify
        notify_ids = set([req["createdBy"]] + ADMINS + MANAGERS)
        mention_str = " ".join(f"<@{uid}>" for uid in notify_ids)
        send_discord_notification(
            f"💬 New comment on **{req['gameName']}** by <@{current_user}>: {comment_text}\n"
            f"Notifying: {mention_str}"
        )

        return jsonify({"message": "Comment added successfully"}), 200

    except Exception as e:
        print("❌ Error in POST /request/<id>/comment:")
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500

# DELETE /request/<id>/comment/<index> → Remove comment if owner or admin
@app.route("/request/<id>/comment/<int:index>", methods=["DELETE"])
def delete_comment(id, index):
    try:
        data = request.get_json(force=True)
        current_user = data.get("currentUserId", "")

        req = requests_collection.find_one({"_id": ObjectId(id)})
        if not req:
            return jsonify({"error": "Request not found"}), 404

        comments = req.get("comments", [])
        # Syntax fixed: compare with length of comments
        if index < 0 or index >= len(comments):
            return jsonify({"error": "Comment index out of bounds"}), 400

        comment = comments[index]
        owner = comment.get("userId", "")

        # Only owner or admin can delete
        if owner != current_user and current_user not in ADMINS:
            return jsonify({"error": "Not authorized to delete this comment"}), 403

        # Pull that exact comment object and update lastActivity
        requests_collection.update_one(
            {"_id": ObjectId(id)},
            {
                "$pull": {"comments": comment},
                "$set":  {"lastActivity": datetime.utcnow()}
            }
        )

        send_discord_notification(
            f"🗑️ Comment deleted on **{req['gameName']}** by <@{current_user}>"
        )

        return jsonify({"message": "Comment deleted successfully"}), 200

    except Exception as e:
        print("❌ Error in DELETE /request/<id>/comment/<index>:")
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", 5000)))
