import os
import math
from typing import Any

import httpx

from app.models import Coordinate


MAPBOX_TOKEN = os.getenv("MAPBOX_TOKEN", "")


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


def _to_polyline(coords: list[list[float]]) -> list[dict[str, float]]:
    return [{"lat": c[1], "lng": c[0]} for c in coords]


def _fallback_alternatives(origin: Coordinate, destination: Coordinate) -> list[dict[str, Any]]:
    # Build two curved alternatives so the route renders as an actual road-like path.
    dist = max(_distance_km(origin, destination), 0.15)
    mid_lat = (origin.lat + destination.lat) / 2
    mid_lng = (origin.lng + destination.lng) / 2
    lat_delta = destination.lat - origin.lat
    lng_delta = destination.lng - origin.lng
    mag = max(abs(lat_delta) + abs(lng_delta), 0.0001)
    # Perpendicular offset
    off_lat = -(lng_delta / mag) * 0.008
    off_lng = (lat_delta / mag) * 0.008

    fastest_poly = [
        origin.model_dump(),
        {"lat": mid_lat + off_lat * 0.35, "lng": mid_lng + off_lng * 0.35},
        {"lat": mid_lat + off_lat * 0.70, "lng": mid_lng + off_lng * 0.70},
        destination.model_dump(),
    ]
    safer_poly = [
        origin.model_dump(),
        {"lat": mid_lat - off_lat * 0.25, "lng": mid_lng - off_lng * 0.25},
        {"lat": mid_lat - off_lat * 0.75, "lng": mid_lng - off_lng * 0.75},
        destination.model_dump(),
    ]

    base_eta = max(2, int(round((dist / 34.0) * 60)))
    return [
        {
            "eta_minutes": base_eta,
            "distance_km": round(dist * 1.03, 2),
            "polyline": fastest_poly,
            "traffic_density": round(min(0.85, 0.3 + dist / 40.0), 2),
        },
        {
            "eta_minutes": base_eta + 3,
            "distance_km": round(dist * 1.12, 2),
            "polyline": safer_poly,
            "traffic_density": round(min(0.80, 0.25 + dist / 42.0), 2),
        },
    ]


async def get_route_alternatives(origin: Coordinate, destination: Coordinate) -> list[dict[str, Any]]:
    """
    Returns route alternatives following road geometry.
    - Mapbox (if MAPBOX_TOKEN is present)
    - OSRM public routing (fallback)
    - Deterministic local alternatives if both fail
    """
    if MAPBOX_TOKEN:
        url = (
            f"https://api.mapbox.com/directions/v5/mapbox/driving-traffic/"
            f"{origin.lng},{origin.lat};{destination.lng},{destination.lat}"
        )
        params = {
            "alternatives": "true",
            "geometries": "geojson",
            "overview": "simplified",
            "access_token": MAPBOX_TOKEN,
        }
        async with httpx.AsyncClient(timeout=12) as client:
            resp = await client.get(url, params=params)
            resp.raise_for_status()
            data = resp.json()
            routes: list[dict[str, Any]] = []
            for route in data.get("routes", [])[:3]:
                coords = route["geometry"]["coordinates"]
                routes.append(
                    {
                        "eta_minutes": int(route["duration"] / 60),
                        "distance_km": round(route["distance"] / 1000, 2),
                        "polyline": _to_polyline(coords),
                        "traffic_density": 0.65,
                    }
                )
            if routes:
                return routes

    try:
        osrm_url = (
            f"https://router.project-osrm.org/route/v1/driving/"
            f"{origin.lng},{origin.lat};{destination.lng},{destination.lat}"
        )
        osrm_params = {
            "alternatives": "true",
            "overview": "full",
            "geometries": "geojson",
            "steps": "false",
        }
        async with httpx.AsyncClient(timeout=12) as client:
            resp = await client.get(osrm_url, params=osrm_params)
            resp.raise_for_status()
            data = resp.json()
            routes: list[dict[str, Any]] = []
            for route in data.get("routes", [])[:3]:
                coords = route["geometry"]["coordinates"]
                routes.append(
                    {
                        "eta_minutes": int(route["duration"] / 60),
                        "distance_km": round(route["distance"] / 1000, 2),
                        "polyline": _to_polyline(coords),
                        "traffic_density": 0.5,
                    }
                )
            if routes:
                return routes
    except Exception:
        # Use deterministic local routes if external providers are unavailable.
        pass

    return _fallback_alternatives(origin, destination)
