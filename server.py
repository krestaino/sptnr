from flask import Flask, request, jsonify
import subprocess
import threading
import os
from dotenv import load_dotenv
import functools

load_dotenv()

sptnr = Flask(__name__)
WEB_API_KEY = os.getenv("WEB_API_KEY")
ENABLE_WEB_API_KEY = os.getenv("ENABLE_WEB_API_KEY", "True") == "True"
LOG_DIR = "data/logs"


def api_key_required(f):
    @functools.wraps(f)
    def decorated_function(*args, **kwargs):
        if ENABLE_WEB_API_KEY and request.args.get("api_key") != WEB_API_KEY:
            return jsonify({"error": "Unauthorized"}), 401
        return f(*args, **kwargs)

    return decorated_function


def run_script(cmd):
    subprocess.run(cmd)


@sptnr.route("/process", methods=["GET", "POST"])
@api_key_required
def process_request():
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


@sptnr.route("/logs")
@api_key_required
def list_logs():
    try:
        logs = os.listdir(LOG_DIR)
        logs = [log for log in logs if log.endswith(".log")]  # Filter log files

        log_links = "".join(f'<li><a href="/logs/{log}">{log}</a></li>' for log in logs)
        return f"<h1>Log Files</h1><ul>{log_links}</ul>"
    except Exception as e:
        return f"An error occurred: {e}", 500


@sptnr.route("/logs/<filename>")
@api_key_required
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
    sptnr.run(debug=False, host="0.0.0.0", port=3333)
