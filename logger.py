#!/usr/bin/env python3
"""Hourly İSPARK occupancy snapshot logger.

Fetches the current İSPARK parking status and appends one row per
parking lot to a daily CSV file under data/YYYY-MM/YYYY-MM-DD.csv.

The workflow fires every 10 minutes because GitHub's scheduled runs are
best-effort and get dropped under load. Only the first successful run of
each clock hour writes anything; later runs in the same hour exit early,
so the CSV keeps at most one snapshot per hour.
"""

import csv
import os
import sys
import time
import traceback
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

import requests

API_URL = "https://api.ibb.gov.tr/ispark/Park"
TIMEOUT_SECONDS = 15
MAX_ATTEMPTS = 3
BACKOFF_BASE_SECONDS = 2

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, "data")
LOGS_DIR = os.path.join(BASE_DIR, "logs")
ERROR_LOG_PATH = os.path.join(LOGS_DIR, "errors.log")

ISTANBUL_TZ = ZoneInfo("Europe/Istanbul")

CSV_COLUMNS = [
    "fetch_utc",
    "fetch_istanbul",
    "parkID",
    "parkName",
    "district",
    "lat",
    "lng",
    "capacity",
    "emptyCapacity",
    "occupancy",
    "parkType",
    "isOpen",
    "freeTime",
    "workHours",
]


def log_error(message):
    os.makedirs(LOGS_DIR, exist_ok=True)
    timestamp = datetime.now(timezone.utc).isoformat()
    with open(ERROR_LOG_PATH, "a", encoding="utf-8") as f:
        f.write(f"[{timestamp}] {message}\n")


def csv_path_for(now_istanbul):
    month_dir = os.path.join(DATA_DIR, now_istanbul.strftime("%Y-%m"))
    return os.path.join(month_dir, now_istanbul.strftime("%Y-%m-%d") + ".csv")


def last_logged_hour(csv_path):
    """Return the Istanbul hour of the final row, or None if unavailable.

    Rows are only ever appended, so the last line is the most recent
    snapshot. Read the tail instead of parsing the whole file, which grows
    to roughly a megabyte over a full day.
    """
    if not os.path.isfile(csv_path):
        return None
    try:
        with open(csv_path, "rb") as f:
            f.seek(0, os.SEEK_END)
            size = f.tell()
            window = min(size, 8192)
            f.seek(size - window)
            tail = f.read(window).decode("utf-8", errors="replace")
    except OSError as exc:
        log_error(f"could not read tail of {csv_path}: {exc}")
        return None

    for line in reversed(tail.splitlines()):
        line = line.strip()
        if not line or line.startswith("fetch_utc"):
            continue
        try:
            fetch_istanbul = next(csv.reader([line]))[1]
            return datetime.fromisoformat(fetch_istanbul).hour
        except (StopIteration, IndexError, ValueError):
            continue
    return None


def fetch_parks():
    last_error = None
    for attempt in range(1, MAX_ATTEMPTS + 1):
        try:
            response = requests.get(API_URL, timeout=TIMEOUT_SECONDS)
            response.raise_for_status()
            data = response.json()
            if not isinstance(data, list):
                raise ValueError(f"unexpected response type: {type(data).__name__}")
            return data
        except Exception as exc:
            last_error = exc
            log_error(f"attempt {attempt}/{MAX_ATTEMPTS} failed: {exc}")
            if attempt < MAX_ATTEMPTS:
                time.sleep(BACKOFF_BASE_SECONDS ** attempt)
    raise RuntimeError(f"all {MAX_ATTEMPTS} attempts failed: {last_error}")


def is_valid_park(park):
    capacity = park.get("capacity")
    if not isinstance(capacity, (int, float)) or capacity <= 0:
        return False
    lat = park.get("lat")
    lng = park.get("lng")
    if lat in (None, "") or lng in (None, ""):
        return False
    try:
        float(lat)
        float(lng)
    except (TypeError, ValueError):
        return False
    return True


def build_rows(parks, fetch_utc, fetch_istanbul):
    rows = []
    for park in parks:
        if not is_valid_park(park):
            continue
        capacity = park.get("capacity")
        empty_capacity = park.get("emptyCapacity")
        occupancy = None
        if isinstance(empty_capacity, (int, float)):
            occupancy = capacity - empty_capacity
        rows.append({
            "fetch_utc": fetch_utc,
            "fetch_istanbul": fetch_istanbul,
            "parkID": park.get("parkID"),
            "parkName": park.get("parkName"),
            "district": park.get("district"),
            "lat": park.get("lat"),
            "lng": park.get("lng"),
            "capacity": capacity,
            "emptyCapacity": empty_capacity,
            "occupancy": occupancy,
            "parkType": park.get("parkType"),
            "isOpen": park.get("isOpen"),
            "freeTime": park.get("freeTime"),
            "workHours": park.get("workHours"),
        })
    return rows


def write_rows(rows, now_istanbul):
    csv_path = csv_path_for(now_istanbul)
    os.makedirs(os.path.dirname(csv_path), exist_ok=True)

    file_exists = os.path.isfile(csv_path)
    with open(csv_path, "a", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=CSV_COLUMNS)
        if not file_exists:
            writer.writeheader()
        writer.writerows(rows)

    return csv_path


def main():
    now_utc = datetime.now(timezone.utc)
    now_istanbul = now_utc.astimezone(ISTANBUL_TZ)
    fetch_utc = now_utc.isoformat()
    fetch_istanbul = now_istanbul.isoformat()

    csv_path = csv_path_for(now_istanbul)
    if last_logged_hour(csv_path) == now_istanbul.hour:
        print(f"hour {now_istanbul.hour:02d} already logged, skipping")
        return 0

    try:
        parks = fetch_parks()
    except Exception as exc:
        log_error(f"fetch failed permanently: {exc}")
        return 1

    rows = build_rows(parks, fetch_utc, fetch_istanbul)
    if not rows:
        log_error("fetch succeeded but no valid rows to write")
        return 1

    try:
        csv_path = write_rows(rows, now_istanbul)
    except Exception as exc:
        log_error(f"failed to write CSV: {exc}")
        return 1

    print(f"wrote {len(rows)} rows to {csv_path}")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception:
        log_error("unhandled exception:\n" + traceback.format_exc())
        sys.exit(1)
