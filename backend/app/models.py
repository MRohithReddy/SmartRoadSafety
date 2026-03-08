from datetime import datetime
from typing import Literal, Optional

from pydantic import BaseModel, Field

#has all the business logic

class Coordinate(BaseModel):
    lat: float
    lng: float


class RoadSegment(BaseModel):
    id: str
    name: str
    start: Coordinate
    end: Coordinate
    base_accident_risk: float = Field(ge=0.0)
    safety_score: int = Field(ge=1, le=5)
    category: Literal["safe", "moderate", "risk-prone"]
    color: Literal["green", "yellow", "red"]


class SafetyRoadsRequest(BaseModel):
    time_of_day: Literal["day", "night"] = "day"
    traffic_density: float = Field(ge=0.0, le=1.0, default=0.4)


class RouteRequest(BaseModel):
    origin: Coordinate
    destination: Coordinate
    time_of_day: Literal["day", "night"] = "day"
    traffic_density: Optional[float] = Field(default=None, ge=0.0, le=1.0)


class RouteOption(BaseModel):
    route_type: Literal["safest", "fastest"]
    eta_minutes: int
    distance_km: float
    safety_score: int = Field(ge=1, le=5)
    polyline: list[Coordinate]


class RouteComparisonResponse(BaseModel):
    fastest: RouteOption
    safest: RouteOption


class TrackingStartRequest(BaseModel):
    user_id: str
    started_at: datetime


class TrackingUpdateRequest(BaseModel):
    user_id: str
    location: Coordinate
    moving: bool
    timestamp: datetime


class InactivityCheckRequest(BaseModel):
    user_id: str
    now: datetime
    inactivity_threshold_seconds: int = 120
    countdown_seconds: int = 30


class InactivityCheckResponse(BaseModel):
    inactive: bool
    seconds_inactive: int
    send_alert: bool
    countdown_started: bool
    countdown_seconds_left: int
    emergency_shared: bool


class SOSRequest(BaseModel):
    user_id: str
    location: Coordinate
    timestamp: datetime
    emergency_email: str
    trigger_call: bool = False


class GuardianShareRequest(BaseModel):
    user_id: str
    guardian_email: str
    location: Coordinate
    tracking_started: bool = False
    destination_reached: bool = False
    inactivity_detected: bool = False
    origin: Optional[Coordinate] = None
    destination: Optional[Coordinate] = None
