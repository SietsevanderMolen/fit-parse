#!/usr/bin/env python3
"""Parse Garmin/ANT FIT files and produce detailed workout summaries."""

from __future__ import annotations

import argparse
import json
import math
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from statistics import mean
from typing import Any

import fitdecode


MPS_TO_KMH = 3.6
MPS_TO_MIN_PER_KM = 1000 / 60


@dataclass
class RecordPoint:
    timestamp: datetime | None = None
    heart_rate: int | None = None
    enhanced_speed_mps: float | None = None
    speed_mps: float | None = None
    cadence: int | None = None
    power: int | None = None
    altitude_m: float | None = None
    distance_m: float | None = None
    temperature_c: float | None = None


@dataclass
class FitActivityData:
    session_fields: dict[str, Any] = field(default_factory=dict)
    lap_fields: list[dict[str, Any]] = field(default_factory=list)
    event_fields: list[dict[str, Any]] = field(default_factory=list)
    records: list[RecordPoint] = field(default_factory=list)
    sport_counts: dict[str, int] = field(default_factory=lambda: defaultdict(int))


def _to_epoch_iso(dt: datetime | None) -> str | None:
    if dt is None:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.isoformat()


def _safe_float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _safe_int(value: Any) -> int | None:
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _field_map(frame: fitdecode.records.FitDataMessage) -> dict[str, Any]:
    data: dict[str, Any] = {}
    for field in frame.fields:
        data[field.name] = field.value
    return data


def parse_fit_file(path: str) -> FitActivityData:
    activity = FitActivityData()

    with fitdecode.FitReader(path) as fit:
        for frame in fit:
            if not isinstance(frame, fitdecode.records.FitDataMessage):
                continue

            name = frame.name
            fields = _field_map(frame)

            if name == "session":
                activity.session_fields.update(fields)
                sport = fields.get("sport")
                if sport:
                    activity.sport_counts[str(sport)] += 1

            elif name == "lap":
                activity.lap_fields.append(fields)

            elif name == "event":
                activity.event_fields.append(fields)

            elif name == "sport":
                sport_name = fields.get("sport")
                if sport_name:
                    activity.sport_counts[str(sport_name)] += 1

            elif name == "record":
                activity.records.append(
                    RecordPoint(
                        timestamp=fields.get("timestamp"),
                        heart_rate=_safe_int(fields.get("heart_rate")),
                        enhanced_speed_mps=_safe_float(fields.get("enhanced_speed")),
                        speed_mps=_safe_float(fields.get("speed")),
                        cadence=_safe_int(fields.get("cadence")),
                        power=_safe_int(fields.get("power")),
                        altitude_m=_safe_float(fields.get("enhanced_altitude") or fields.get("altitude")),
                        distance_m=_safe_float(fields.get("distance")),
                        temperature_c=_safe_float(fields.get("temperature")),
                    )
                )

    return activity


def _compute_elapsed_seconds(records: list[RecordPoint], session_fields: dict[str, Any]) -> float | None:
    total = _safe_float(session_fields.get("total_elapsed_time"))
    if total and total > 0:
        return total

    timestamps = [r.timestamp for r in records if r.timestamp is not None]
    if len(timestamps) >= 2:
        return (max(timestamps) - min(timestamps)).total_seconds()

    return None


def _compute_moving_seconds(records: list[RecordPoint], session_fields: dict[str, Any]) -> float | None:
    total = _safe_float(session_fields.get("total_timer_time"))
    if total and total > 0:
        return total
    return _compute_elapsed_seconds(records, session_fields)


def _compute_distance_m(records: list[RecordPoint], session_fields: dict[str, Any]) -> float | None:
    total = _safe_float(session_fields.get("total_distance"))
    if total and total > 0:
        return total

    distances = [r.distance_m for r in records if r.distance_m is not None]
    if distances:
        return max(distances)

    return None


def _compute_avg_speed_mps(records: list[RecordPoint], session_fields: dict[str, Any], distance_m: float | None, moving_s: float | None) -> float | None:
    total = _safe_float(session_fields.get("avg_speed"))
    if total and total > 0:
        return total

    speeds = [r.enhanced_speed_mps or r.speed_mps for r in records if (r.enhanced_speed_mps or r.speed_mps)]
    if speeds:
        return mean(speeds)

    if distance_m and moving_s and moving_s > 0:
        return distance_m / moving_s

    return None


def _compute_max_speed_mps(records: list[RecordPoint], session_fields: dict[str, Any]) -> float | None:
    total = _safe_float(session_fields.get("max_speed"))
    if total and total > 0:
        return total

    speeds = [r.enhanced_speed_mps or r.speed_mps for r in records if (r.enhanced_speed_mps or r.speed_mps)]
    if speeds:
        return max(speeds)

    return None


def _compute_hr_stats(records: list[RecordPoint], session_fields: dict[str, Any]) -> tuple[float | None, int | None]:
    avg_hr = _safe_float(session_fields.get("avg_heart_rate"))
    max_hr = _safe_int(session_fields.get("max_heart_rate"))

    hr_values = [r.heart_rate for r in records if r.heart_rate is not None]
    if avg_hr is None and hr_values:
        avg_hr = mean(hr_values)
    if max_hr is None and hr_values:
        max_hr = max(hr_values)

    return avg_hr, max_hr


def _compute_power_stats(records: list[RecordPoint], session_fields: dict[str, Any]) -> tuple[float | None, int | None]:
    avg_power = _safe_float(session_fields.get("avg_power"))
    max_power = _safe_int(session_fields.get("max_power"))

    values = [r.power for r in records if r.power is not None]
    if avg_power is None and values:
        avg_power = mean(values)
    if max_power is None and values:
        max_power = max(values)

    return avg_power, max_power


def _compute_cadence_stats(records: list[RecordPoint], session_fields: dict[str, Any]) -> tuple[float | None, int | None]:
    avg_cadence = _safe_float(session_fields.get("avg_cadence"))
    max_cadence = _safe_int(session_fields.get("max_cadence"))

    values = [r.cadence for r in records if r.cadence is not None]
    if avg_cadence is None and values:
        avg_cadence = mean(values)
    if max_cadence is None and values:
        max_cadence = max(values)

    return avg_cadence, max_cadence


def _compute_altitude(records: list[RecordPoint], session_fields: dict[str, Any]) -> tuple[float | None, float | None]:
    gain = _safe_float(session_fields.get("total_ascent"))
    loss = _safe_float(session_fields.get("total_descent"))

    altitudes = [r.altitude_m for r in records if r.altitude_m is not None]
    if altitudes and (gain is None or loss is None):
        ascent = 0.0
        descent = 0.0
        for a, b in zip(altitudes[:-1], altitudes[1:]):
            diff = b - a
            if diff > 0:
                ascent += diff
            elif diff < 0:
                descent += abs(diff)
        if gain is None:
            gain = ascent
        if loss is None:
            loss = descent

    return gain, loss


def _compute_temperature_stats(records: list[RecordPoint], session_fields: dict[str, Any]) -> tuple[float | None, float | None]:
    avg_temp = _safe_float(session_fields.get("avg_temperature"))
    max_temp = _safe_float(session_fields.get("max_temperature"))

    values = [r.temperature_c for r in records if r.temperature_c is not None]
    if values:
        if avg_temp is None:
            avg_temp = mean(values)
        if max_temp is None:
            max_temp = max(values)

    return avg_temp, max_temp


def _fmt_duration(seconds: float | None) -> str:
    if seconds is None:
        return "n/a"
    return str(timedelta(seconds=int(round(seconds))))


def _fmt_distance(meters: float | None) -> str:
    if meters is None:
        return "n/a"
    return f"{meters / 1000:.2f} km"


def _fmt_speed(speed_mps: float | None) -> str:
    if speed_mps is None:
        return "n/a"
    return f"{speed_mps * MPS_TO_KMH:.2f} km/h"


def _fmt_pace(speed_mps: float | None) -> str:
    if speed_mps is None or speed_mps <= 0:
        return "n/a"
    min_per_km = MPS_TO_MIN_PER_KM / speed_mps
    mins = int(min_per_km)
    secs = int(round((min_per_km - mins) * 60))
    if secs == 60:
        mins += 1
        secs = 0
    return f"{mins}:{secs:02d} min/km"


def summarize_activity(activity: FitActivityData, source_path: str) -> dict[str, Any]:
    session = activity.session_fields
    records = activity.records

    start_time = session.get("start_time")
    if start_time is None:
        timestamps = [r.timestamp for r in records if r.timestamp is not None]
        start_time = min(timestamps) if timestamps else None

    elapsed_s = _compute_elapsed_seconds(records, session)
    moving_s = _compute_moving_seconds(records, session)
    distance_m = _compute_distance_m(records, session)
    avg_speed_mps = _compute_avg_speed_mps(records, session, distance_m, moving_s)
    max_speed_mps = _compute_max_speed_mps(records, session)
    avg_hr, max_hr = _compute_hr_stats(records, session)
    avg_power, max_power = _compute_power_stats(records, session)
    avg_cadence, max_cadence = _compute_cadence_stats(records, session)
    ascent_m, descent_m = _compute_altitude(records, session)
    avg_temp, max_temp = _compute_temperature_stats(records, session)

    sport = session.get("sport")
    sub_sport = session.get("sub_sport")
    if sport is None and activity.sport_counts:
        sport = max(activity.sport_counts.items(), key=lambda kv: kv[1])[0]

    event_types = defaultdict(int)
    for event in activity.event_fields:
        event_name = event.get("event")
        event_type = event.get("event_type")
        key = f"{event_name}:{event_type}" if event_name or event_type else "unknown"
        event_types[key] += 1

    laps_summary: list[dict[str, Any]] = []
    for idx, lap in enumerate(activity.lap_fields, start=1):
        lap_distance = _safe_float(lap.get("total_distance"))
        lap_time = _safe_float(lap.get("total_timer_time") or lap.get("total_elapsed_time"))
        lap_avg_speed = _safe_float(lap.get("avg_speed"))
        if lap_avg_speed is None and lap_distance and lap_time and lap_time > 0:
            lap_avg_speed = lap_distance / lap_time

        laps_summary.append(
            {
                "lap": idx,
                "duration_s": lap_time,
                "distance_m": lap_distance,
                "avg_speed_mps": lap_avg_speed,
                "avg_hr": _safe_float(lap.get("avg_heart_rate")),
                "max_hr": _safe_int(lap.get("max_heart_rate")),
                "avg_power": _safe_float(lap.get("avg_power")),
                "avg_cadence": _safe_float(lap.get("avg_cadence")),
            }
        )

    summary: dict[str, Any] = {
        "source": source_path,
        "sport": str(sport) if sport is not None else None,
        "sub_sport": str(sub_sport) if sub_sport is not None else None,
        "device": {
            "manufacturer": session.get("manufacturer"),
            "product": session.get("product"),
        },
        "timing": {
            "start_time": _to_epoch_iso(start_time),
            "elapsed_s": elapsed_s,
            "moving_s": moving_s,
            "elapsed_hms": _fmt_duration(elapsed_s),
            "moving_hms": _fmt_duration(moving_s),
        },
        "distance": {
            "meters": distance_m,
            "km": round(distance_m / 1000, 3) if distance_m is not None else None,
        },
        "speed": {
            "avg_mps": avg_speed_mps,
            "max_mps": max_speed_mps,
            "avg_kmh": round(avg_speed_mps * MPS_TO_KMH, 3) if avg_speed_mps is not None else None,
            "max_kmh": round(max_speed_mps * MPS_TO_KMH, 3) if max_speed_mps is not None else None,
            "avg_pace_min_per_km": round((MPS_TO_MIN_PER_KM / avg_speed_mps), 3) if avg_speed_mps else None,
        },
        "heart_rate": {
            "avg_bpm": round(avg_hr, 1) if avg_hr is not None else None,
            "max_bpm": max_hr,
        },
        "power": {
            "avg_w": round(avg_power, 1) if avg_power is not None else None,
            "max_w": max_power,
        },
        "cadence": {
            "avg_rpm": round(avg_cadence, 1) if avg_cadence is not None else None,
            "max_rpm": max_cadence,
        },
        "elevation": {
            "ascent_m": round(ascent_m, 1) if ascent_m is not None else None,
            "descent_m": round(descent_m, 1) if descent_m is not None else None,
        },
        "temperature": {
            "avg_c": round(avg_temp, 1) if avg_temp is not None else None,
            "max_c": round(max_temp, 1) if max_temp is not None else None,
        },
        "energy": {
            "calories_kcal": _safe_float(session.get("total_calories")),
            "training_stress_score": _safe_float(session.get("training_stress_score")),
        },
        "laps": laps_summary,
        "record_count": len(records),
        "lap_count": len(activity.lap_fields),
        "event_counts": dict(event_types),
    }

    return summary


def render_text_summary(summary: dict[str, Any]) -> str:
    lines: list[str] = []
    lines.append(f"Source: {summary['source']}")
    lines.append(
        f"Activity: {summary.get('sport') or 'unknown'}"
        + (f" ({summary.get('sub_sport')})" if summary.get("sub_sport") else "")
    )

    timing = summary["timing"]
    lines.append(f"Start Time: {timing.get('start_time') or 'n/a'}")
    lines.append(
        f"Duration: moving {timing.get('moving_hms')} | elapsed {timing.get('elapsed_hms')}"
    )

    distance_m = summary["distance"].get("meters")
    lines.append(f"Distance: {_fmt_distance(distance_m)}")

    speed = summary["speed"]
    lines.append(
        "Speed/Pace: "
        f"avg {_fmt_speed(speed.get('avg_mps'))} ({_fmt_pace(speed.get('avg_mps'))}), "
        f"max {_fmt_speed(speed.get('max_mps'))}"
    )

    hr = summary["heart_rate"]
    lines.append(f"Heart Rate: avg {hr.get('avg_bpm') or 'n/a'} bpm, max {hr.get('max_bpm') or 'n/a'} bpm")

    power = summary["power"]
    if power.get("avg_w") is not None or power.get("max_w") is not None:
        lines.append(f"Power: avg {power.get('avg_w') or 'n/a'} W, max {power.get('max_w') or 'n/a'} W")

    cadence = summary["cadence"]
    if cadence.get("avg_rpm") is not None or cadence.get("max_rpm") is not None:
        lines.append(
            f"Cadence: avg {cadence.get('avg_rpm') or 'n/a'} rpm, max {cadence.get('max_rpm') or 'n/a'} rpm"
        )

    elev = summary["elevation"]
    if elev.get("ascent_m") is not None or elev.get("descent_m") is not None:
        lines.append(
            f"Elevation: +{elev.get('ascent_m') or 'n/a'} m / -{elev.get('descent_m') or 'n/a'} m"
        )

    temp = summary["temperature"]
    if temp.get("avg_c") is not None or temp.get("max_c") is not None:
        lines.append(f"Temperature: avg {temp.get('avg_c') or 'n/a'} C, max {temp.get('max_c') or 'n/a'} C")

    energy = summary["energy"]
    if energy.get("calories_kcal") is not None:
        lines.append(f"Calories: {energy['calories_kcal']} kcal")

    lines.append(f"Laps: {summary['lap_count']} | Records: {summary['record_count']}")

    if summary["laps"]:
        lines.append("Lap Breakdown:")
        for lap in summary["laps"]:
            lap_dist = _fmt_distance(lap.get("distance_m"))
            lap_duration = _fmt_duration(lap.get("duration_s"))
            lap_speed = _fmt_speed(lap.get("avg_speed_mps"))
            lap_hr = lap.get("avg_hr")
            lines.append(
                f"  Lap {lap['lap']}: {lap_dist}, {lap_duration}, {lap_speed}, "
                f"avg HR {round(lap_hr, 1) if lap_hr is not None else 'n/a'}"
            )

    return "\n".join(lines)


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Summarize FIT exercise files with fitdecode")
    parser.add_argument("fit_file", help="Path to input .fit file")
    parser.add_argument("--json", action="store_true", help="Print JSON summary")
    parser.add_argument(
        "--pretty-json",
        action="store_true",
        help="Print pretty-formatted JSON summary",
    )
    return parser


def main() -> int:
    parser = build_arg_parser()
    args = parser.parse_args()

    activity = parse_fit_file(args.fit_file)
    summary = summarize_activity(activity, source_path=args.fit_file)

    if args.json or args.pretty_json:
        indent = 2 if args.pretty_json else None
        print(json.dumps(summary, default=str, indent=indent))
    else:
        print(render_text_summary(summary))

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
