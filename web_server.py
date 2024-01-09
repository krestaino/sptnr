from flask import Flask, request, jsonify
import json
import subprocess
import threading
import os
from dotenv import load_dotenv
import datetime

load_dotenv()

sptnr_web_server = Flask(__name__)
API_KEY = os.getenv("WEB_API_KEY")
LOG_DIR = "data/logs"


def run_script(cmd):
    subprocess.run(cmd)


def log_post_data(data):
    timestamp = datetime.datetime.now().isoformat()
    log_filename = os.path.join(LOG_DIR, f"log_{timestamp}.txt")
    with open(log_filename, "w") as log_file:
        json.dump(data, log_file, indent=4)


@sptnr_web_server.route("/process", methods=["GET", "POST"])
def process_request():
    if request.args.get("api_key") != API_KEY:
        return jsonify({"error": "Unauthorized"}), 401

    cmd = ["python3", "sptnr.py"]
    if request.args.get("preview", "") == "true":
        cmd.append("--preview")
    if request.args.get("force", "") == "true":
        cmd.append("--force")
    artist_ids = request.args.getlist("artist")
    for artist_id in artist_ids:
        cmd.extend(["--artist", artist_id])
    album_ids = request.args.getlist("album")
    for album_id in album_ids:
        cmd.extend(["--album", album_id])
    start = request.args.get("start")
    if start:
        cmd.extend(["--start", start])
    limit = request.args.get("limit")
    if limit:
        cmd.extend(["--limit", limit])

    thread = threading.Thread(target=run_script, args=(cmd,))
    thread.start()

    return jsonify({"message": "Processing started"})


@sptnr_web_server.route("/logs")
def list_logs():
    try:
        logs = os.listdir(LOG_DIR)
        logs = [log for log in logs if log.endswith(".log")]  # Filter log files

        log_links = "".join(f'<li><a href="/logs/{log}">{log}</a></li>' for log in logs)
        return f"<h1>Log Files</h1><ul>{log_links}</ul>"
    except Exception as e:
        return f"An error occurred: {e}", 500


@sptnr_web_server.route("/logs/<filename>")
def view_log(filename):
    try:
        full_path = os.path.join(LOG_DIR, filename)
        if not os.path.exists(full_path) or not os.path.isfile(full_path):
            return "File not found", 404

        with open(full_path, "r") as file:
            content = file.read()

        # Convert content to HTML-friendly format
        content = content.replace("\n", "<br>")
        return f'<h1>{filename}</h1><div style="white-space: pre-wrap;">{content}</div>'
    except Exception as e:
        return f"An error occurred: {e}", 500


if __name__ == "__main__":
    sptnr_web_server.run(debug=False, host="0.0.0.0", port=3333)
