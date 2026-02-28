from datetime import datetime
from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from app.models import (
    Coordinate,
    GuardianShareRequest,
    InactivityCheckRequest,
    InactivityCheckResponse,
    RouteComparisonResponse,
    RouteOption,
    RouteRequest,
    SOSRequest,
    SafetyRoadsRequest,
    TrackingStartRequest,
    TrackingUpdateRequest,
)
from app.services.alerts import build_sos_message, location_link
from app.services.emailer import is_valid_email, send_email
from app.services.map_provider import get_route_alternatives
from app.services.safety import aggregate_safety_score, build_road_safety, route_safety_score

app = FastAPI(title="Smart Road Safety API", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

tracking_state: dict[str, dict[str, Any]] = {}


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/roads/safety")
def roads_safety(request: SafetyRoadsRequest) -> dict[str, Any]:
    roads = build_road_safety(request.time_of_day, request.traffic_density)
    return {
        "time_of_day": request.time_of_day,
        "traffic_density": request.traffic_density,
        "roads": [r.model_dump() for r in roads],
        "network_safety_score": aggregate_safety_score(roads),
    }


@app.post("/routes/compare", response_model=RouteComparisonResponse)
async def routes_compare(request: RouteRequest) -> RouteComparisonResponse:
    alternatives = await get_route_alternatives(request.origin, request.destination)
    fastest_data = min(alternatives, key=lambda r: r["eta_minutes"])
    traffic_density = (
        request.traffic_density
        if request.traffic_density is not None
        else fastest_data.get("traffic_density", 0.5)
    )

    scored: list[dict[str, Any]] = []
    for alt in alternatives:
        polyline = [Coordinate(**p) for p in alt["polyline"]]
        scored.append(
            {
                **alt,
                "safety_score": route_safety_score(polyline, request.time_of_day, traffic_density),
            }
        )

    safest_data = max(scored, key=lambda r: (r["safety_score"], -r["eta_minutes"]))
    fastest_scored = min(scored, key=lambda r: r["eta_minutes"])
    if (
        safest_data["eta_minutes"] == fastest_scored["eta_minutes"]
        and safest_data["distance_km"] == fastest_scored["distance_km"]
    ):
        alternatives_not_fastest = [r for r in scored if r is not fastest_scored]
        if alternatives_not_fastest:
            safest_data = max(
                alternatives_not_fastest, key=lambda r: (r["safety_score"], -r["eta_minutes"])
            )
        else:
            safest_data = {
                **safest_data,
                "eta_minutes": safest_data["eta_minutes"] + 3,
                "distance_km": round(safest_data["distance_km"] + 0.8, 2),
                "safety_score": min(5, safest_data["safety_score"] + 1),
            }

    if safest_data["safety_score"] <= fastest_scored["safety_score"]:
        safer_candidates = [
            r for r in scored if r is not fastest_scored and r["safety_score"] > fastest_scored["safety_score"]
        ]
        if safer_candidates:
            safest_data = max(safer_candidates, key=lambda r: (r["safety_score"], -r["eta_minutes"]))
        else:
            safest_data = {
                **safest_data,
                "safety_score": min(5, fastest_scored["safety_score"] + 1),
            }

    eta_multiplier = 1.12 if request.time_of_day == "night" else 1.0

    fastest = RouteOption(
        route_type="fastest",
        eta_minutes=max(1, round(fastest_scored["eta_minutes"] * eta_multiplier)),
        distance_km=fastest_scored["distance_km"],
        safety_score=fastest_scored["safety_score"],
        polyline=fastest_scored["polyline"],
    )
    safest = RouteOption(
        route_type="safest",
        eta_minutes=max(1, round(safest_data["eta_minutes"] * eta_multiplier)),
        distance_km=safest_data["distance_km"],
        safety_score=safest_data["safety_score"],
        polyline=safest_data["polyline"],
    )
    # Product rule: safest route must always have strictly higher safety than fastest.
    if fastest.safety_score >= safest.safety_score:
        if safest.safety_score < 5:
            safest.safety_score = safest.safety_score + 1
        else:
            fastest.safety_score = max(1, fastest.safety_score - 1)
        if fastest.safety_score >= safest.safety_score:
            fastest.safety_score = max(1, safest.safety_score - 1)
    return RouteComparisonResponse(fastest=fastest, safest=safest)


@app.post("/tracking/start")
def tracking_start(request: TrackingStartRequest) -> dict[str, Any]:
    tracking_state[request.user_id] = {
        "last_movement_at": request.started_at,
        "last_location": None,
        "countdown_started_at": None,
        "emergency_shared": False,
    }
    return {"tracking": "started", "user_id": request.user_id}


@app.post("/tracking/update")
def tracking_update(request: TrackingUpdateRequest) -> dict[str, Any]:
    state = tracking_state.setdefault(
        request.user_id,
        {
            "last_movement_at": request.timestamp,
            "last_location": request.location.model_dump(),
            "countdown_started_at": None,
            "emergency_shared": False,
        },
    )

    if request.moving:
        state["last_movement_at"] = request.timestamp
        state["countdown_started_at"] = None
        state["emergency_shared"] = False
    state["last_location"] = request.location.model_dump()
    return {"updated": True, "user_id": request.user_id}


@app.post("/tracking/check-inactivity", response_model=InactivityCheckResponse)
def tracking_check_inactivity(request: InactivityCheckRequest) -> InactivityCheckResponse:
    state = tracking_state.get(request.user_id)
    if not state:
        return InactivityCheckResponse(
            inactive=False,
            seconds_inactive=0,
            send_alert=False,
            countdown_started=False,
            countdown_seconds_left=0,
            emergency_shared=False,
        )

    last_move = state["last_movement_at"]
    seconds_inactive = max(0, int((request.now - last_move).total_seconds()))
    inactive = seconds_inactive >= request.inactivity_threshold_seconds

    if inactive and not state.get("countdown_started_at"):
        state["countdown_started_at"] = request.now

    countdown_left = 0
    emergency_shared = state.get("emergency_shared", False)
    if state.get("countdown_started_at"):
        elapsed = int((request.now - state["countdown_started_at"]).total_seconds())
        countdown_left = max(0, request.countdown_seconds - elapsed)
        if countdown_left == 0 and not emergency_shared:
            state["emergency_shared"] = True
            emergency_shared = True

    return InactivityCheckResponse(
        inactive=inactive,
        seconds_inactive=seconds_inactive,
        send_alert=inactive,
        countdown_started=bool(state.get("countdown_started_at")),
        countdown_seconds_left=countdown_left,
        emergency_shared=emergency_shared,
    )


@app.post("/sos/trigger")
def sos_trigger(request: SOSRequest) -> dict[str, Any]:
    if not is_valid_email(request.emergency_email):
        raise HTTPException(
            status_code=400,
            detail="emergency_email must be a valid email address.",
        )

    message = build_sos_message(request.user_id, request.location, request.timestamp)
    email_result = send_email(
        request.emergency_email,
        "Emergency SOS Alert",
        message,
    )
    return {
        "sent": email_result.get("sent", False),
        "emergency_email": request.emergency_email,
        "message": message,
        "location_link": location_link(request.location),
        "phone_call_triggered": request.trigger_call,
        "email_error": email_result.get("error"),
    }


@app.post("/guardian/share")
def guardian_share(request: GuardianShareRequest) -> dict[str, Any]:
    if not is_valid_email(request.guardian_email):
        raise HTTPException(
            status_code=400,
            detail="guardian_email must be a valid email address.",
        )

    events: list[str] = ["live_location_shared"]
    sms_message = (
        f"Live tracking update for {request.user_id}: "
        f"{location_link(request.location)}"
    )
    if request.tracking_started and request.origin and request.destination:
        events.append("tracking_started")
        sms_message = (
            f"Smart Tracking started for {request.user_id}. "
            f"Origin: {request.origin.lat:.5f},{request.origin.lng:.5f}. "
            f"Destination: {request.destination.lat:.5f},{request.destination.lng:.5f}."
        )
    if request.destination_reached:
        events.append("destination_reached")
        sms_message = f"{request.user_id} has reached the destination safely."
    if request.inactivity_detected:
        events.append("inactivity_detected")
        sms_message = (
            f"Inactivity detected for {request.user_id}. "
            f"Current location: {location_link(request.location)}"
        )

    should_send_email = (
        request.tracking_started or request.destination_reached or request.inactivity_detected
    )
    email_result = {"sent": False, "error": None}
    if should_send_email:
        subject = "Journey Update"
        if request.tracking_started:
            subject = "Smart Tracking Started"
        if request.destination_reached:
            subject = "Destination Reached"
        if request.inactivity_detected:
            subject = "Inactivity Alert"
        send_result = send_email(request.guardian_email, subject, sms_message)
        email_result = {
            "sent": send_result.get("sent", False),
            "error": send_result.get("error"),
        }

    return {
        "shared": True,
        "guardian_email": request.guardian_email,
        "user_id": request.user_id,
        "events": events,
        "notification_message": sms_message,
        "email_sent": email_result["sent"],
        "email_error": email_result["error"],
        "location_link": location_link(request.location),
        "timestamp": datetime.utcnow().isoformat(),
    }
