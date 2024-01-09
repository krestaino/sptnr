with open("VERSION", "r") as file:
    __version__ = file.read().strip()

import argparse
import base64
import json
import logging
import os
import re
import sys
import time
import urllib.parse

from dotenv import load_dotenv
import requests
from colorama import init, Fore, Style
from tqdm import tqdm

# Load environment variables from .env file if it exists
if os.path.exists(".env"):
    load_dotenv()

# Record the start time
start_time = time.time()

# Config
NAV_BASE_URL = os.getenv("NAV_BASE_URL")
NAV_USER = os.getenv("NAV_USER")
NAV_PASS = os.getenv("NAV_PASS")
SPOTIFY_CLIENT_ID = os.getenv("SPOTIFY_CLIENT_ID")
SPOTIFY_CLIENT_SECRET = os.getenv("SPOTIFY_CLIENT_SECRET")

# Colors
LIGHT_PURPLE = Fore.MAGENTA + Style.BRIGHT
LIGHT_GREEN = Fore.GREEN + Style.BRIGHT
LIGHT_RED = Fore.RED + Style.BRIGHT
LIGHT_BLUE = Fore.BLUE + Style.BRIGHT
LIGHT_CYAN = Fore.CYAN + Style.BRIGHT
LIGHT_YELLOW = Fore.YELLOW + Style.BRIGHT
BOLD = Style.BRIGHT
RESET = Style.RESET_ALL

# Setup logs
LOG_DIR = "data/logs"
if not os.path.exists(LOG_DIR):
    os.makedirs(LOG_DIR)

LOGFILE = os.path.join(LOG_DIR, f"sptnr_{int(time.time())}.log")


class NoColorFormatter(logging.Formatter):
    ansi_escape = re.compile(r"\x1B\[[0-?]*[ -/]*[@-~]")

    def format(self, record):
        record.msg = self.ansi_escape.sub("", record.msg)
        return super(NoColorFormatter, self).format(record)


# Set up the stream handler (console logging) without timestamp
logging.basicConfig(
    level=logging.INFO, format="%(message)s", handlers=[logging.StreamHandler()]
)

# Set up the file handler (file logging) with timestamp
file_handler = logging.FileHandler(LOGFILE, "a")
file_handler.setFormatter(NoColorFormatter("[%(asctime)s] %(message)s"))
logging.getLogger().addHandler(file_handler)

# Auth
HEX_ENCODED_PASS = NAV_PASS.encode().hex()
TOKEN_AUTH = base64.b64encode(
    f"{SPOTIFY_CLIENT_ID}:{SPOTIFY_CLIENT_SECRET}".encode()
).decode()
TOKEN_URL = "https://accounts.spotify.com/api/token"
response = requests.post(
    TOKEN_URL,
    headers={"Authorization": f"Basic {TOKEN_AUTH}"},
    data={"grant_type": "client_credentials"},
)

if response.status_code != 200:
    error_info = response.json()  # Assuming the error response is in JSON format
    error_description = error_info.get("error_description", "Unknown error")
    logging.error(
        f"{LIGHT_RED}Spotify Authentication Error: {error_description}{RESET}"
    )
    sys.exit(1)

SPOTIFY_TOKEN = response.json()["access_token"]

init(autoreset=True)

# Default flags
PREVIEW = 0
START = 0
LIMIT = 0
ARTIST_IDs = []
ALBUM_IDs = []

# Variables
ARTISTS_PROCESSED = 0
TOTAL_TRACKS = 0
FOUND_AND_UPDATED = 0
NOT_FOUND = 0
UNMATCHED_TRACKS = []
PROCESSED_ALBUMS_FILE = "data/processed_albums.txt"

processed_albums = set()

# Parse arguments
description_text = "process command-line flags for sync"
parser = argparse.ArgumentParser()

parser.add_argument(
    "-p",
    "--preview",
    action="store_true",
    help="execute script in preview mode (no changes made)",
)
parser.add_argument(
    "-a",
    "--artist",
    action="append",
    help="process the artist using the Navidrome artist ID (ignores START and LIMIT)",
    type=str,
)
parser.add_argument(
    "-b",
    "--album",
    action="append",
    help="process the album using the Navidrome album ID (ignores START and LIMIT)",
    type=str,
)
parser.add_argument(
    "-s",
    "--start",
    default=0,
    type=int,
    help="start processing from artist at index [NUM] (0-based index, so 0 is the first artist)",
)
parser.add_argument(
    "-l",
    "--limit",
    default=0,
    type=int,
    help="limit to processing [NUM] artists from the start index",
)

parser.add_argument(
    "-v", "--version", action="version", version=f"%(prog)s {__version__}"
)

parser.add_argument(
    "-f",
    "--force",
    action="store_true",
    help="force processing of all albums, even if they were processed previously",
)


args = parser.parse_args()

ARTIST_IDs = args.artist if args.artist else []
ALBUM_IDs = args.album if args.album else []
START = args.start
LIMIT = args.limit

logging.info(f"{BOLD}Version:{RESET} {LIGHT_YELLOW}sptnr v{__version__}{RESET}")

if args.preview:
    logging.info(f"{LIGHT_YELLOW}Preview mode, no changes will be made.{RESET}")
    PREVIEW = 1

# Check if both ARTIST_ID and START/LIMIT are provided
if ARTIST_IDs and (START != 0 or LIMIT != 0):
    START = 0
    LIMIT = 0
    logging.info(
        f"{LIGHT_YELLOW}Warning: The --artist flag overrides --start and --limit. Ignoring these settings.{RESET}"
    )

if not args.preview:
    logging.info(
        f"{BOLD}Syncing Spotify {LIGHT_CYAN}popularity{RESET}{BOLD} with Navidrome {LIGHT_BLUE}rating{RESET}...{RESET}"
    )


def validate_url(url):
    if not re.match(r"https?://", url):
        logging.error(
            f"{LIGHT_RED}Config Error: URL must start with 'http://' or 'https://'.{RESET}"
        )
        return False
    if url.endswith("/"):
        logging.error(
            f"{LIGHT_RED}Config Error: URL must not end with a trailing slash.{RESET}"
        )
        return False
    return True


def url_encode(string):
    return urllib.parse.quote_plus(string)


def get_rating_from_popularity(popularity):
    popularity = float(popularity)
    if popularity < 16.66:
        return 0
    elif popularity < 33.33:
        return 1
    elif popularity < 50:
        return 2
    elif popularity < 66.66:
        return 3
    elif popularity < 83.33:
        return 4
    else:
        return 5


def process_track(track_id, artist_name, album, track_name):
    def search_spotify(query):
        spotify_url = f"https://api.spotify.com/v1/search?q={query}&type=track&limit=1"
        headers = {"Authorization": f"Bearer {SPOTIFY_TOKEN}"}

        try:
            response = requests.get(spotify_url, headers=headers)
        except requests.exceptions.ConnectionError:
            logging.error(f"{LIGHT_RED}Spotify Error: Unable to reach server.{RESET}")
            sys.exit(1)

        if response.status_code != 200:
            if response.status_code == 429:
                logging.error(
                    f"{LIGHT_RED}Spotify Error {response.status_code}: Retry after {BOLD}{response.headers.get('Retry-After', 'some time')}s{RESET}"
                )
            else:
                logging.error(
                    f"{LIGHT_RED}Spotify Error {response.status_code}: {response.text}{RESET}"
                )
            sys.exit(1)
        try:
            return response.json()
        except ValueError as e:
            logging.error(
                f"{LIGHT_RED}Spotify Error: Error decoding JSON from Spotify API: {e}{RESET}"
            )
            sys.exit(1)

    def remove_parentheses_content(s):
        """Remove content inside parentheses from a string."""
        return re.sub(r"\s*\(.*?\)\s*", " ", s).strip()

    encoded_track_name = url_encode(track_name)
    encoded_artist_name = url_encode(artist_name)
    encoded_album = url_encode(album)

    # Primary Search (with album)
    spotify_data = search_spotify(
        f"{encoded_track_name}%20artist:{encoded_artist_name}%20album:{encoded_album}"
    )

    found_track = len(spotify_data.get("tracks", {}).get("items", [])) > 0

    if not found_track:
        # Secondary Search (without album and parentheses content)
        sanitized_track_name = url_encode(remove_parentheses_content(track_name))
        spotify_data = search_spotify(
            f"{sanitized_track_name}%20artist:{encoded_artist_name}"
        )
        found_track = len(spotify_data.get("tracks", {}).get("items", [])) > 0

    if not found_track:
        # Tertiary Search (replace 'Part' with 'Pt.')
        modified_track_name = track_name.replace("Part", "Pt.")
        encoded_modified_track_name = url_encode(modified_track_name)
        spotify_data = search_spotify(
            f"{encoded_modified_track_name}%20artist:{encoded_artist_name}"
        )
        found_track = len(spotify_data.get("tracks", {}).get("items", []))

    if found_track:
        popularity = spotify_data["tracks"]["items"][0].get("popularity", 0)
        rating = get_rating_from_popularity(popularity)
        popularity_str = f"{popularity} " if 0 <= popularity <= 9 else str(popularity)
        message = f"    p:{LIGHT_CYAN}{popularity_str}{RESET} → r:{LIGHT_BLUE}{rating}{RESET} | {LIGHT_GREEN}{track_name}{RESET}"
        logging.info(message)
        if PREVIEW != 1:
            nav_url = f"{NAV_BASE_URL}/rest/setRating?u={NAV_USER}&p=enc:{HEX_ENCODED_PASS}&v=1.12.0&c=myapp&id={track_id}&rating={rating}"
            requests.get(nav_url)
        global FOUND_AND_UPDATED
        FOUND_AND_UPDATED += 1
    else:
        logging.info(
            f"    p:{LIGHT_RED}??{RESET} → r:{LIGHT_BLUE}0{RESET} | {LIGHT_RED}(not found) {track_name}{RESET}"
        )
        global UNMATCHED_TRACKS
        UNMATCHED_TRACKS.append(f"{artist_name} - {album} - {track_name}")
        global NOT_FOUND
        NOT_FOUND += 1

    global TOTAL_TRACKS
    TOTAL_TRACKS += 1


def process_album(album_id):
    if not args.force:
        global processed_albums

        if album_id in processed_albums:
            logging.info(f"    {LIGHT_CYAN}Skipping already processed album{RESET}")
            return

    nav_url = f"{NAV_BASE_URL}/rest/getAlbum?id={album_id}&u={NAV_USER}&p=enc:{HEX_ENCODED_PASS}&v=1.12.0&c=spotify_sync&f=json"
    response = requests.get(nav_url).json()

    album_info = response["subsonic-response"]["album"]
    album_artist = album_info["artist"]
    tracks = [
        (song["id"], album_artist, song["album"], song["title"])
        for song in album_info.get("song", [])
    ]

    for track in tracks:
        process_track(*track)

    processed_albums.add(album_id)
    with open(PROCESSED_ALBUMS_FILE, "a") as file:
        file.write(f"{album_id}\n")


def process_artist(artist_id):
    nav_url = f"{NAV_BASE_URL}/rest/getArtist?id={artist_id}&u={NAV_USER}&p=enc:{HEX_ENCODED_PASS}&v=1.12.0&c=spotify_sync&f=json"
    response = requests.get(nav_url).json()

    albums = [
        (album["id"], album["name"])
        for album in response["subsonic-response"]["artist"].get("album", [])
    ]

    for album_id, album_name in albums:
        logging.info(f"  Album: {LIGHT_YELLOW}{album_name}{RESET} ({album_id})")
        process_album(album_id)


def fetch_data(url):
    try:
        response = requests.get(url)
        response_data = json.loads(response.text)

        if "subsonic-response" not in response_data:
            logging.error(
                f"{LIGHT_RED}Unexpected response format from Navidrome.{RESET}"
            )
            sys.exit(1)

        nav_response = response_data["subsonic-response"]

        if "error" in nav_response:
            error_message = nav_response["error"].get("message", "Unknown error")
            logging.error(f"{LIGHT_RED}Navidrome Error: {error_message}{RESET}")
            sys.exit(1)

        return nav_response

    except requests.exceptions.ConnectionError:
        logging.error(
            f"{LIGHT_RED}Connection Error: Failed to connect to the provided URL. Please check if the URL is correct and the server is reachable.{RESET}"
        )
        sys.exit(1)
    except requests.exceptions.RequestException as e:
        logging.error(
            f"{LIGHT_RED}Connection Error: An error occurred while trying to connect to Navidrome: {e}{RESET}"
        )
        sys.exit(1)
    except json.JSONDecodeError:
        logging.error(
            f"{LIGHT_RED}JSON Parsing Error: Failed to parse JSON response from Navidrome. Please check if the provided URL is a valid Navidrome server.{RESET}"
        )
        sys.exit(1)


# Load processed albums
if os.path.exists(PROCESSED_ALBUMS_FILE) and not args.force:
    with open(PROCESSED_ALBUMS_FILE, "r") as file:
        processed_albums = set(file.read().splitlines())

try:
    validate_url(NAV_BASE_URL)
except ValueError as e:
    logging.error(f"{LIGHT_RED}{e}{RESET}")
    sys.exit(1)

if ARTIST_IDs:
    for ARTIST_ID in ARTIST_IDs:
        url = f"{NAV_BASE_URL}/rest/getArtist?id={ARTIST_ID}&u={NAV_USER}&p=enc:{HEX_ENCODED_PASS}&v=1.12.0&c=spotify_sync&f=json"
        data = fetch_data(url)
        ARTIST_NAME = data["artist"]["name"]

        logging.info("")
        logging.info(f"Artist: {LIGHT_PURPLE}{ARTIST_NAME}{RESET} ({ARTIST_ID})")
        process_artist(ARTIST_ID)

elif ALBUM_IDs:
    for ALBUM_ID in ALBUM_IDs:
        url = f"{NAV_BASE_URL}/rest/getAlbum?id={ALBUM_ID}&u={NAV_USER}&p=enc:{HEX_ENCODED_PASS}&v=1.12.0&c=spotify_sync&f=json"
        data = fetch_data(url)
        ARTIST_NAME = data["album"]["artist"]
        ARTIST_ID = data["album"]["artistId"]
        ALBUM_NAME = data["album"]["name"]

        logging.info("")
        logging.info(f"Artist: {LIGHT_PURPLE}{ARTIST_NAME}{RESET} ({ARTIST_ID})")
        logging.info(f"  Album: {LIGHT_YELLOW}{ALBUM_NAME}{RESET} ({ALBUM_ID})")
        process_album(ALBUM_ID)

else:
    url = f"{NAV_BASE_URL}/rest/getArtists?u={NAV_USER}&p=enc:{HEX_ENCODED_PASS}&v=1.12.0&c=spotify_sync&f=json"
    data = fetch_data(url)
    ARTIST_DATA = [
        (artist["id"], artist["name"])
        for index_entry in data["artists"]["index"]
        for artist in index_entry["artist"]
    ]

    if START == 0 and LIMIT == 0:
        data_slice = ARTIST_DATA
        total_count = len(ARTIST_DATA)
    else:
        if LIMIT == 0:
            data_slice = ARTIST_DATA[START:]
        else:
            data_slice = ARTIST_DATA[START : START + LIMIT]
        total_count = len(data_slice)

    logging.info(f"Total artists to process: {LIGHT_GREEN}{total_count}{RESET}")

    for index, ARTIST_ENTRY in tqdm(
        enumerate(data_slice), total=total_count, leave=False, unit="artist"
    ):
        ARTIST_ID, ARTIST_NAME = ARTIST_ENTRY

        logging.info("")
        logging.info(
            f"Artist: {LIGHT_PURPLE}{ARTIST_NAME}{RESET} ({ARTIST_ID})[{index}]"
        )
        process_artist(ARTIST_ID)

        ARTISTS_PROCESSED += 1


# Display the results
logging.info("")

# Check if TOTAL_TRACKS is zero to avoid division by zero error
if TOTAL_TRACKS > 0:
    MATCH_PERCENTAGE = (FOUND_AND_UPDATED / TOTAL_TRACKS) * 100
else:
    MATCH_PERCENTAGE = 0

FORMATTED_MATCH_PERCENTAGE = round(MATCH_PERCENTAGE, 2)
TOTAL_BLOCKS = 20

color_found = LIGHT_GREEN if FOUND_AND_UPDATED == TOTAL_TRACKS else LIGHT_YELLOW
color_found_white = LIGHT_GREEN if FOUND_AND_UPDATED == TOTAL_TRACKS else BOLD
color_not_found = LIGHT_GREEN if NOT_FOUND == 0 else LIGHT_RED

# Adjust the progress bar calculation
blocks_found = (
    "█" * round(FOUND_AND_UPDATED * TOTAL_BLOCKS / TOTAL_TRACKS)
    if TOTAL_TRACKS > 0
    else ""
)
blocks_not_found = "█" * (TOTAL_BLOCKS - len(blocks_found))
full_blocks_found = f"{color_found_white}{blocks_found}{RESET}"
full_blocks_not_found = f"{color_not_found}{blocks_not_found}{RESET}"

# Calculate elapsed time
elapsed_time = time.time() - start_time
hours, remainder = divmod(elapsed_time, 3600)
minutes, seconds = divmod(remainder, 60)

parts = []
if hours:
    parts.append(f"{int(hours)}h")
if minutes:
    parts.append(f"{int(minutes)}m")
if seconds or not parts:  # Show seconds if it's the only value, even if it's 0
    parts.append(f"{int(seconds)}s")

formatted_elapsed_time = " ".join(parts)

logging.info(
    f"Tracks: {LIGHT_PURPLE}{TOTAL_TRACKS}{RESET} | Found: {color_found}{FOUND_AND_UPDATED}{RESET} |{full_blocks_found}{full_blocks_not_found}| Not Found: {color_not_found}{NOT_FOUND}{RESET} | Match: {color_found}{FORMATTED_MATCH_PERCENTAGE}%{RESET} | Time: {LIGHT_PURPLE}{formatted_elapsed_time}{RESET}"
)
