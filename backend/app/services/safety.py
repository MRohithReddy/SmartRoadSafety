import csv
from dataclasses import dataclass
from functools import lru_cache
import math
from pathlib import Path
from typing import Iterable

from app.models import Coordinate, RoadSegment


DATA_FILE = Path(__file__).resolve().parents[2] / "data" / "accidents_sample.csv"


@dataclass(frozen=True)
class AccidentPoint:
    lat: float
    lng: float
    severity: int
    hour: int


def _distance_km(a: Coordinate, b: Coordinate) -> float:
    r = 6371.0
    d_lat = math.radians(b.lat - a.lat)
    d_lng = math.radians(b.lng - a.lng)
    s = (
        math.sin(d_lat / 2) ** 2
        + math.cos(math.radians(a.lat))
        * math.cos(math.radians(b.lat))
        * math.sin(d_lng / 2) ** 2
    )
    return 2 * r * math.asin(math.sqrt(s))


@lru_cache(maxsize=1)
def _accident_points() -> list[AccidentPoint]:
    rows: list[AccidentPoint] = []
    with DATA_FILE.open("r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            rows.append(
                AccidentPoint(
                    lat=float(row["lat"]),
                    lng=float(row["lng"]),
                    severity=max(1, min(5, int(row.get("severity", 2)))),
                    hour=max(0, min(23, int(row.get("hour", 12)))),
                )
            )
    return rows


def _road_templates() -> Iterable[tuple[str, str, Coordinate, Coordinate]]:
    return [
        (
            "r1",
            "Outer Ring Road, Bengaluru",
            Coordinate(lat=12.9469, lng=77.6266),
            Coordinate(lat=12.9716, lng=77.6412),
        ),
        (
            "r2",
            "Western Express Hwy, Mumbai",
            Coordinate(lat=19.0977, lng=72.8764),
            Coordinate(lat=19.1509, lng=72.8544),
        ),
        (
            "r3",
            "Ring Road, Delhi",
            Coordinate(lat=28.6129, lng=77.2295),
            Coordinate(lat=28.6417, lng=77.2167),
        ),
        (
            "r4",
            "OMR, Chennai",
            Coordinate(lat=12.9298, lng=80.2270),
            Coordinate(lat=12.9865, lng=80.2473),
        ),
    ]


def _risk_to_score(risk: float) -> int:
    # risk [0..1] -> score [5..1]
    if risk <= 0.15:
        return 5
    if risk <= 0.33:
        return 4
    if risk <= 0.52:
        return 3
    if risk <= 0.72:
        return 2
    return 1


def _score_to_category(score: int) -> tuple[str, str]:
    if score >= 4:
        return "safe", "green"
    if score == 3:
        return "moderate", "yellow"
    return "risk-prone", "red"


def build_road_safety(time_of_day: str, traffic_density: float) -> list[RoadSegment]:
    points = _accident_points()
    roads: list[RoadSegment] = []
    night_modifier = 0.12 if time_of_day == "night" else 0.0
    traffic_modifier = min(max(traffic_density, 0.0), 1.0) * 0.25

    for road_id, name, start, end in _road_templates():
        # Accident concentration around midpoint.
        midpoint = Coordinate(lat=(start.lat + end.lat) / 2, lng=(start.lng + end.lng) / 2)
        nearby_weight = 0.0
        for p in points:
            p_coord = Coordinate(lat=p.lat, lng=p.lng)
            d = _distance_km(midpoint, p_coord)
            if d <= 1.2:
                nearby_weight += (p.severity / 5.0) * max(0.0, 1.0 - d / 1.2)
        accident_risk = min(nearby_weight / 4.5, 1.0)

        combined_risk = min(accident_risk * 0.7 + traffic_modifier + night_modifier, 1.0)
        score = _risk_to_score(combined_risk)
        category, color = _score_to_category(score)

        roads.append(
            RoadSegment(
                id=road_id,
                name=name,
                start=start,
                end=end,
                base_accident_risk=round(accident_risk, 3),
                safety_score=score,
                category=category,  # type: ignore[arg-type]
                color=color,  # type: ignore[arg-type]
            )
        )
    return roads


def aggregate_safety_score(roads: list[RoadSegment]) -> int:
    if not roads:
        return 3
    return max(1, min(5, round(sum(r.safety_score for r in roads) / len(roads))))


def _is_night_hour(hour: int) -> bool:
    return hour >= 20 or hour <= 5


def _time_alignment_factor(accident_hour: int, time_of_day: str) -> float:
    if time_of_day == "night":
        return 1.2 if _is_night_hour(accident_hour) else 0.7
    return 1.1 if not _is_night_hour(accident_hour) else 0.75


def _polyline_length_km(polyline: list[Coordinate]) -> float:
    if len(polyline) < 2:
        return 0.0
    return sum(_distance_km(polyline[i], polyline[i + 1]) for i in range(len(polyline) - 1))


def _route_complexity(polyline: list[Coordinate]) -> float:
    if len(polyline) < 3:
        return 0.0
    turns = 0
    samples = 0
    for i in range(1, len(polyline) - 1):
        a = polyline[i - 1]
        b = polyline[i]
        c = polyline[i + 1]
        v1 = (b.lat - a.lat, b.lng - a.lng)
        v2 = (c.lat - b.lat, c.lng - b.lng)
        mag1 = math.hypot(v1[0], v1[1])
        mag2 = math.hypot(v2[0], v2[1])
        if mag1 == 0 or mag2 == 0:
            continue
        dot = max(-1.0, min(1.0, (v1[0] * v2[0] + v1[1] * v2[1]) / (mag1 * mag2)))
        angle_deg = math.degrees(math.acos(dot))
        if angle_deg >= 35:
            turns += 1
        samples += 1
    if samples == 0:
        return 0.0
    return min(turns / samples, 1.0)


RISK_ZONES = [
    # India-specific higher-risk urban traffic/conflict zones (sample risk grid).
    {"lat": 28.6280, "lng": 77.2188, "radius_km": 2.2, "risk": 0.50},  # Delhi Connaught Place
    {"lat": 28.5562, "lng": 77.1000, "radius_km": 2.4, "risk": 0.42},  # Delhi Airport corridor
    {"lat": 19.0760, "lng": 72.8777, "radius_km": 2.8, "risk": 0.48},  # Mumbai central
    {"lat": 19.1197, "lng": 72.8468, "radius_km": 2.0, "risk": 0.40},  # Andheri
    {"lat": 12.9716, "lng": 77.5946, "radius_km": 2.6, "risk": 0.46},  # Bengaluru CBD
    {"lat": 12.9352, "lng": 77.6245, "radius_km": 2.2, "risk": 0.38},  # Koramangala-ORR
    {"lat": 13.0827, "lng": 80.2707, "radius_km": 2.5, "risk": 0.43},  # Chennai central
    {"lat": 13.0500, "lng": 80.2500, "radius_km": 2.0, "risk": 0.36},  # OMR corridor
    {"lat": 17.3850, "lng": 78.4867, "radius_km": 2.4, "risk": 0.41},  # Hyderabad central
    {"lat": 22.5726, "lng": 88.3639, "radius_km": 2.7, "risk": 0.44},  # Kolkata central
    {"lat": 18.5204, "lng": 73.8567, "radius_km": 2.2, "risk": 0.39},  # Pune central
    {"lat": 23.0225, "lng": 72.5714, "radius_km": 2.3, "risk": 0.37},  # Ahmedabad central
]


def _zone_risk(polyline: list[Coordinate]) -> float:
    if not polyline:
        return 0.0
    sample = polyline[:: max(1, len(polyline) // 30)]
    if not sample:
        sample = polyline
    total = 0.0
    for p in sample:
        p_coord = Coordinate(lat=p.lat, lng=p.lng)
        for z in RISK_ZONES:
            center = Coordinate(lat=z["lat"], lng=z["lng"])
            d = _distance_km(p_coord, center)
            if d <= z["radius_km"]:
                total += z["risk"] * max(0.0, 1.0 - d / z["radius_km"])
    return min(total / max(1.0, len(sample) * 1.2), 1.0)


def route_safety_score(polyline: list[Coordinate], time_of_day: str, traffic_density: float) -> int:
    if not polyline:
        return 3
    points = _accident_points()
    sample = polyline[:: max(1, len(polyline) // 30)]
    if not sample:
        sample = polyline

    proximity_risk = 0.0
    for s in sample:
        local_weight = 0.0
        for a in points:
            d = _distance_km(s, Coordinate(lat=a.lat, lng=a.lng))
            if d <= 0.7:
                severity_weight = 0.6 + (a.severity / 5.0)
                time_weight = _time_alignment_factor(a.hour, time_of_day)
                local_weight += severity_weight * time_weight * max(0.0, 1.0 - d / 0.7)
        proximity_risk += min(local_weight / 4.5, 1.0)

    accident_risk = min(proximity_risk / max(1, len(sample)), 1.0)
    zone_risk = _zone_risk(polyline)
    complexity_risk = _route_complexity(polyline) * 0.5
    length_risk = min(_polyline_length_km(polyline) / 40.0, 0.25)
    night_modifier = 0.14 if time_of_day == "night" else 0.02
    traffic_modifier = min(max(traffic_density, 0.0), 1.0) * 0.22
    combined_risk = min(
        accident_risk * 0.42
        + zone_risk * 0.22
        + complexity_risk * 0.14
        + length_risk * 0.08
        + traffic_modifier
        + night_modifier,
        1.0,
    )
    return _risk_to_score(combined_risk)
