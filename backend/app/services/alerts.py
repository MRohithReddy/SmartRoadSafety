from datetime import datetime

from app.models import Coordinate


def location_link(location: Coordinate) -> str:
    return f"https://maps.google.com/?q={location.lat},{location.lng}"


def build_sos_message(user_id: str, location: Coordinate, timestamp: datetime) -> str:
    return (
        f"[SOS] User {user_id} needs help at {timestamp.isoformat()}. "
        f"Location: {location_link(location)}"
    )
