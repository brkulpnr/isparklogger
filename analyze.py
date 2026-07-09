#!/usr/bin/env python3
"""Builds hourly occupancy patterns from the accumulated İSPARK CSV logs.

Reads every data/YYYY-MM/YYYY-MM-DD.csv file and produces:
  - output/hourly_patterns.json: district -> day type -> 24 hourly values (1-5 scale)
  - output/summary.md: busiest districts/parks and data coverage stats
"""

import csv
import glob
import json
import os
from datetime import datetime

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, "data")
OUTPUT_DIR = os.path.join(BASE_DIR, "output")

MIN_OBSERVATIONS = 3
DAY_TYPES = ["weekday", "friday", "saturday", "sunday"]


def day_type_for(weekday):
    if weekday <= 3:  # Mon-Thu
        return "weekday"
    if weekday == 4:
        return "friday"
    if weekday == 5:
        return "saturday"
    return "sunday"


def iter_rows():
    csv_paths = sorted(glob.glob(os.path.join(DATA_DIR, "*", "*.csv")))
    for path in csv_paths:
        with open(path, "r", encoding="utf-8", newline="") as f:
            reader = csv.DictReader(f)
            for row in reader:
                yield row


def to_float(value):
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def main():
    os.makedirs(OUTPUT_DIR, exist_ok=True)

    # (district, day_type, hour) -> [sum_ratio, count]
    district_hourly = {}
    # district -> [sum_ratio, count]
    district_overall = {}
    # (parkID, parkName, district) -> [sum_ratio, count]
    park_overall = {}

    total_rows = 0
    valid_rows = 0
    dates_seen = set()
    districts_seen = set()
    parks_seen = set()

    for row in iter_rows():
        total_rows += 1

        capacity = to_float(row.get("capacity"))
        occupancy = to_float(row.get("occupancy"))
        district = row.get("district")
        fetch_istanbul = row.get("fetch_istanbul")

        if not capacity or capacity <= 0 or occupancy is None or not district or not fetch_istanbul:
            continue

        try:
            dt = datetime.fromisoformat(fetch_istanbul)
        except ValueError:
            continue

        ratio = max(0.0, min(1.0, occupancy / capacity))
        day_type = day_type_for(dt.weekday())
        hour = dt.hour

        dates_seen.add(dt.date().isoformat())
        districts_seen.add(district)

        key = (district, day_type, hour)
        entry = district_hourly.setdefault(key, [0.0, 0])
        entry[0] += ratio
        entry[1] += 1

        d_entry = district_overall.setdefault(district, [0.0, 0])
        d_entry[0] += ratio
        d_entry[1] += 1

        park_id = row.get("parkID")
        park_name = row.get("parkName")
        if park_id:
            park_key = (park_id, park_name, district)
            parks_seen.add(park_key)
            p_entry = park_overall.setdefault(park_key, [0.0, 0])
            p_entry[0] += ratio
            p_entry[1] += 1

        valid_rows += 1

    # --- output/hourly_patterns.json ---
    patterns = {}
    for district in sorted(districts_seen):
        patterns[district] = {}
        for day_type in DAY_TYPES:
            hours = []
            for hour in range(24):
                entry = district_hourly.get((district, day_type, hour))
                if entry is None or entry[1] < MIN_OBSERVATIONS:
                    hours.append(None)
                    continue
                avg_ratio = entry[0] / entry[1]
                score = round(1 + avg_ratio * 4)
                score = max(1, min(5, score))
                hours.append(score)
            patterns[district][day_type] = hours

    with open(os.path.join(OUTPUT_DIR, "hourly_patterns.json"), "w", encoding="utf-8") as f:
        json.dump(patterns, f, ensure_ascii=False, indent=2)

    # --- output/summary.md ---
    busiest_districts = sorted(
        (
            (district, entry[0] / entry[1], entry[1])
            for district, entry in district_overall.items()
            if entry[1] >= MIN_OBSERVATIONS
        ),
        key=lambda item: item[1],
        reverse=True,
    )[:10]

    busiest_parks = sorted(
        (
            (park_key, entry[0] / entry[1], entry[1])
            for park_key, entry in park_overall.items()
            if entry[1] >= MIN_OBSERVATIONS
        ),
        key=lambda item: item[1],
        reverse=True,
    )[:10]

    lines = []
    lines.append("# İSPARK Doluluk Özeti")
    lines.append("")
    lines.append("## Veri Kapsamı")
    lines.append(f"- Toplam satır: {total_rows}")
    lines.append(f"- Geçerli satır: {valid_rows}")
    lines.append(f"- Kapsanan gün sayısı: {len(dates_seen)}")
    if dates_seen:
        lines.append(f"- Tarih aralığı: {min(dates_seen)} -> {max(dates_seen)}")
    lines.append(f"- İlçe sayısı: {len(districts_seen)}")
    lines.append(f"- Otopark sayısı: {len(parks_seen)}")
    lines.append("")
    lines.append("## En Dolu 10 İlçe (ortalama doluluk oranı)")
    if busiest_districts:
        for district, avg_ratio, count in busiest_districts:
            lines.append(f"- {district}: %{avg_ratio * 100:.1f} ({count} gözlem)")
    else:
        lines.append("- Yeterli veri yok.")
    lines.append("")
    lines.append("## En Dolu 10 Otopark (ortalama doluluk oranı)")
    if busiest_parks:
        for (park_id, park_name, district), avg_ratio, count in busiest_parks:
            lines.append(f"- {park_name} ({district}): %{avg_ratio * 100:.1f} ({count} gözlem)")
    else:
        lines.append("- Yeterli veri yok.")
    lines.append("")

    with open(os.path.join(OUTPUT_DIR, "summary.md"), "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")

    print(f"processed {total_rows} rows ({valid_rows} valid) across {len(dates_seen)} days")
    print(f"wrote {os.path.join('output', 'hourly_patterns.json')}")
    print(f"wrote {os.path.join('output', 'summary.md')}")


if __name__ == "__main__":
    main()
