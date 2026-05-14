#!/usr/bin/env python3
"""Parse Garmin/ANT FIT files and produce detailed workout summaries."""

from __future__ import annotations

import argparse
import json
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from statistics import mean
from typing import Any

import fitdecode


MPS_TO_KMH = 3.6
MPS_TO_MIN_PER_KM = 1000 / 60
DEFAULT_DETAIL_INTERVAL = "1m"
DEFAULT_ZONE_SCHEME = "50-60,60-70,70-80,80-90,90-100"


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


def _parse_interval_seconds(interval: str) -> int:
    if len(interval) < 2:
        raise ValueError("Interval must look like '10s', '1m', or '10m'.")
    unit = interval[-1].lower()
    value = int(interval[:-1])
    if value <= 0:
        raise ValueError("Interval must be positive.")
    if unit == "s":
        return value
    if unit == "m":
        return value * 60
    raise ValueError("Interval unit must be 's' or 'm'.")


def _build_interval_metrics(records: list[RecordPoint], bucket_seconds: int) -> list[dict[str, Any]]:
    timed_records = [r for r in records if r.timestamp is not None]
    if not timed_records:
        return []

    base_time = timed_records[0].timestamp
    assert base_time is not None
    buckets: dict[int, list[RecordPoint]] = defaultdict(list)

    for record in timed_records:
        assert record.timestamp is not None
        offset = (record.timestamp - base_time).total_seconds()
        idx = int(offset // bucket_seconds)
        buckets[idx].append(record)

    details: list[dict[str, Any]] = []
    for idx in sorted(buckets):
        points = buckets[idx]
        hr = [p.heart_rate for p in points if p.heart_rate is not None]
        speed = [p.enhanced_speed_mps or p.speed_mps for p in points if (p.enhanced_speed_mps or p.speed_mps)]
        power = [p.power for p in points if p.power is not None]
        cadence = [p.cadence for p in points if p.cadence is not None]
        distance = [p.distance_m for p in points if p.distance_m is not None]

        start_ts = points[0].timestamp
        end_ts = points[-1].timestamp
        details.append(
            {
                "bucket_index": idx,
                "start_time": _to_epoch_iso(start_ts),
                "end_time": _to_epoch_iso(end_ts),
                "avg_hr_bpm": round(mean(hr), 1) if hr else None,
                "min_hr_bpm": min(hr) if hr else None,
                "max_hr_bpm": max(hr) if hr else None,
                "avg_speed_kmh": round(mean(speed) * MPS_TO_KMH, 2) if speed else None,
                "avg_pace_min_per_km": round(MPS_TO_MIN_PER_KM / mean(speed), 3) if speed and mean(speed) > 0 else None,
                "avg_power_w": round(mean(power), 1) if power else None,
                "avg_cadence_rpm": round(mean(cadence), 1) if cadence else None,
                "distance_delta_m": round(max(distance) - min(distance), 2) if len(distance) >= 2 else None,
            }
        )

    return details


def _parse_zone_scheme(zone_scheme: str, zone_mode: str) -> list[tuple[str, float, float]]:
    zones: list[tuple[str, float, float]] = []
    chunks = [chunk.strip() for chunk in zone_scheme.split(",") if chunk.strip()]
    if not chunks:
        raise ValueError("Zone scheme cannot be empty.")

    for idx, chunk in enumerate(chunks, start=1):
        if "-" not in chunk:
            raise ValueError(f"Invalid zone '{chunk}'. Expected form like 70-80.")
        low_str, high_str = chunk.split("-", 1)
        low = float(low_str)
        high = float(high_str)
        if low < 0 or high <= low:
            raise ValueError(f"Invalid zone range '{chunk}'.")
        label = f"z{idx}_{int(low)}_{int(high)}"
        if zone_mode == "percent":
            zones.append((label, low / 100.0, high / 100.0))
        else:
            zones.append((label, low, high))
    return zones


def _build_hr_zones(records: list[RecordPoint], max_hr: int | None, zone_scheme: str, zone_mode: str) -> dict[str, Any] | None:
    if zone_mode == "percent" and not max_hr:
        return None
    hr_values = [r.heart_rate for r in records if r.heart_rate is not None]
    if not hr_values:
        return None

    zones = _parse_zone_scheme(zone_scheme, zone_mode)
    counts: dict[str, int] = {label: 0 for label, _, _ in zones}
    above_highest = 0
    lowest_floor = zones[0][1]
    highest_ceiling = zones[-1][2]

    for hr in hr_values:
        value = (hr / max_hr) if zone_mode == "percent" else float(hr)
        matched = False
        for name, low, high in zones:
            if low <= value < high:
                counts[name] += 1
                matched = True
                break
        if not matched and value >= highest_ceiling:
            above_highest += 1

    total = len(hr_values)
    distribution = {
        k: {
            "samples": v,
            "pct": round((v / total) * 100, 2) if total else 0.0,
        }
        for k, v in counts.items()
    }
    if lowest_floor > 0:
        below = 0
        if zone_mode == "percent":
            below = sum(1 for hr in hr_values if (hr / max_hr) < lowest_floor)
        else:
            below = sum(1 for hr in hr_values if float(hr) < lowest_floor)
        distribution["below_lowest"] = {
            "samples": below,
            "pct": round((below / total) * 100, 2) if total else 0.0,
        }
    if above_highest > 0:
        distribution["above_highest"] = {
            "samples": above_highest,
            "pct": round((above_highest / total) * 100, 2) if total else 0.0,
        }

    return {
        "max_hr_reference_bpm": max_hr,
        "zone_mode": zone_mode,
        "zone_scheme": zone_scheme,
        "distribution": distribution,
    }


def _build_distance_splits(records: list[RecordPoint], split_km: float = 1.0) -> list[dict[str, Any]]:
    threshold_m = split_km * 1000
    splits: list[dict[str, Any]] = []
    segment: list[RecordPoint] = []
    next_split_mark = threshold_m
    split_start_time: datetime | None = None

    for r in records:
        if r.timestamp is None or r.distance_m is None:
            continue
        if split_start_time is None:
            split_start_time = r.timestamp
        segment.append(r)
        if r.distance_m >= next_split_mark:
            split_end_time = r.timestamp
            hr_values = [p.heart_rate for p in segment if p.heart_rate is not None]
            speed_values = [p.enhanced_speed_mps or p.speed_mps for p in segment if (p.enhanced_speed_mps or p.speed_mps)]
            duration_s = (split_end_time - split_start_time).total_seconds() if split_start_time else None
            splits.append(
                {
                    "split_km": round(next_split_mark / 1000, 1),
                    "duration_s": duration_s,
                    "duration_hms": _fmt_duration(duration_s),
                    "avg_hr_bpm": round(mean(hr_values), 1) if hr_values else None,
                    "avg_speed_kmh": round(mean(speed_values) * MPS_TO_KMH, 2) if speed_values else None,
                    "avg_pace_min_per_km": round(MPS_TO_MIN_PER_KM / mean(speed_values), 3)
                    if speed_values and mean(speed_values) > 0
                    else None,
                }
            )
            next_split_mark += threshold_m
            segment = [r]
            split_start_time = r.timestamp

    return splits


def summarize_activity(
    activity: FitActivityData,
    source_path: str,
    detail_interval: str = DEFAULT_DETAIL_INTERVAL,
    hr_zone_scheme: str = DEFAULT_ZONE_SCHEME,
    hr_zone_mode: str = "percent",
) -> dict[str, Any]:
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
    detail_interval_seconds = _parse_interval_seconds(detail_interval)

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
        "coach_detail": {
            "interval": detail_interval,
            "interval_seconds": detail_interval_seconds,
            "interval_metrics": _build_interval_metrics(records, detail_interval_seconds),
            "heart_rate_zones": _build_hr_zones(records, max_hr, hr_zone_scheme, hr_zone_mode),
            "distance_splits_1km": _build_distance_splits(records, split_km=1.0),
        },
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

    coach_detail = summary.get("coach_detail") or {}
    interval = coach_detail.get("interval")
    interval_metrics = coach_detail.get("interval_metrics") or []
    lines.append(f"Detail Buckets: {interval} ({len(interval_metrics)} buckets)")

    hr_zones = coach_detail.get("heart_rate_zones")
    if hr_zones:
        zone_text = []
        for zone_name, data in hr_zones.get("distribution", {}).items():
            zone_text.append(f"{zone_name} {data.get('pct')}%")
        lines.append("HR Zones: " + ", ".join(zone_text))

    splits = coach_detail.get("distance_splits_1km") or []
    if splits:
        preview = splits[:5]
        lines.append("1km Splits (first 5):")
        for s in preview:
            lines.append(
                f"  {s['split_km']} km: {s['duration_hms']}, "
                f"HR {s.get('avg_hr_bpm') or 'n/a'}, pace {s.get('avg_pace_min_per_km') or 'n/a'}"
            )

    return "\n".join(lines)


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Summarize FIT exercise files with fitdecode")
    parser.add_argument("fit_file", help="Path to input .fit file")
    parser.add_argument(
        "--detail-interval",
        default=DEFAULT_DETAIL_INTERVAL,
        help="Detail bucket interval for coach metrics (examples: 10s, 1m, 10m). Default: 1m",
    )
    parser.add_argument(
        "--hr-zone-scheme",
        default=DEFAULT_ZONE_SCHEME,
        help="Comma-separated HR zones. Use with --hr-zone-mode percent (default) or bpm.",
    )
    parser.add_argument(
        "--hr-zone-mode",
        choices=["percent", "bpm"],
        default="percent",
        help="Interpret --hr-zone-scheme as max-HR percentages or absolute BPM zones.",
    )
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
    summary = summarize_activity(
        activity,
        source_path=args.fit_file,
        detail_interval=args.detail_interval,
        hr_zone_scheme=args.hr_zone_scheme,
        hr_zone_mode=args.hr_zone_mode,
    )

    if args.json or args.pretty_json:
        indent = 2 if args.pretty_json else None
        print(json.dumps(summary, default=str, indent=indent))
    else:
        print(render_text_summary(summary))

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
