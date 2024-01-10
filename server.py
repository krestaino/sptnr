from flask import Flask, request, jsonify
import subprocess
import threading
import os
from dotenv import load_dotenv
import functools
import re
import datetime

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
        full_paths = [os.path.join(LOG_DIR, log) for log in logs]
        logs_sorted = sorted(full_paths, key=os.path.getmtime, reverse=True)

        table_rows = []
        for log_path in logs_sorted:
            with open(log_path, "r") as file:
                last_line = file.readlines()[-1]
                tracks, found, not_found, match, time = parse_log_data(last_line)

            log_name = os.path.basename(log_path)
            timestamp = int(log_name.split("_")[1].split(".")[0])
            log_datetime = datetime.datetime.fromtimestamp(timestamp)
            formatted_datetime = log_datetime.strftime("%Y-%m-%d %H:%M:%S")

            table_rows.append(
                f"<tr><td><a href='/logs/{log_name}'>{log_name}</a></td><td>{formatted_datetime}</td><td>{tracks}</td><td>{found}</td><td>{not_found}</td><td>{match}</td><td>{time}</td></tr>"
            )

        table_html = f"<table border='1'><tr><th>Log File</th><th>Date & Time</th><th>Tracks</th><th>Found</th><th>Not Found</th><th>Match</th><th>Time</th></tr>{''.join(table_rows)}</table>"
        return table_html
    except Exception as e:
        return f"An error occurred: {e}", 500


def parse_log_data(line):
    # Regular expressions to extract the required data
    tracks_pattern = r"Tracks: (\d+)"
    found_pattern = r"Found: (\d+)"
    not_found_pattern = r"Not Found: (\d+)"
    match_pattern = r"Match: ([\d.]+%)"
    time_pattern = r"Time: ([\ds]+)"

    # Extracting data using regular expressions
    tracks = re.search(tracks_pattern, line)
    found = re.search(found_pattern, line)
    not_found = re.search(not_found_pattern, line)
    match = re.search(match_pattern, line)
    time = re.search(time_pattern, line)

    # Getting the values or "N/A" if not found
    tracks = tracks.group(1) if tracks else "N/A"
    found = found.group(1) if found else "N/A"
    not_found = not_found.group(1) if not_found else "N/A"
    match = match.group(1) if match else "N/A"
    time = time.group(1) if time else "N/A"

    return tracks, found, not_found, match, time


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
        return f"<pre>{content}</pre>"
    except Exception as e:
        return f"An error occurred: {e}", 500


if __name__ == "__main__":
    sptnr.run(debug=False, host="0.0.0.0", port=3333)
