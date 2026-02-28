import { useEffect, useMemo, useState } from "react";
import { MapContainer, Marker, Polyline, Popup, TileLayer, useMap } from "react-leaflet";
import {
  checkInactivity,
  compareRoutes,
  shareGuardian,
  startTracking,
  triggerSOS,
  updateTracking,
} from "./api";

const defaultOrigin = { lat: 40.7412, lng: -73.9895 };
const defaultDestination = { lat: 40.7219, lng: -73.9958 };

function badgeForScore(score) {
  if (score >= 4) return "safe";
  if (score === 3) return "moderate";
  return "risk-prone";
}

function MapAutoFocus({ points }) {
  const map = useMap();

  useEffect(() => {
    if (!points || points.length === 0) return;
    if (points.length === 1) {
      map.setView(points[0], 14, { animate: true });
      return;
    }
    map.fitBounds(points, { padding: [40, 40], animate: true });
  }, [map, points]);

  return null;
}

export default function App() {
  const [timeOfDay, setTimeOfDay] = useState("day");
  const [routeData, setRouteData] = useState(null);
  const [origin, setOrigin] = useState(defaultOrigin);
  const [destination, setDestination] = useState(defaultDestination);

  const [userId] = useState("demo-user-1");
  const [guardianEmail, setGuardianEmail] = useState("guardian@example.com");
  const [emergencyEmail, setEmergencyEmail] = useState("emergency@example.com");
  const [trackingActive, setTrackingActive] = useState(false);
  const [currentLocation, setCurrentLocation] = useState(defaultOrigin);
  const [inactivity, setInactivity] = useState(null);
  const [inactivityAck, setInactivityAck] = useState(false);
  const [autoEscalated, setAutoEscalated] = useState(false);
  const [statusMessage, setStatusMessage] = useState("");

  const mapCenter = useMemo(
    () => [(origin.lat + destination.lat) / 2, (origin.lng + destination.lng) / 2],
    [origin, destination]
  );
  const routeFocusPoints = useMemo(() => {
    if (routeData?.safest?.polyline?.length) {
      return routeData.safest.polyline.map((p) => [p.lat, p.lng]);
    }
    return [
      [origin.lat, origin.lng],
      [destination.lat, destination.lng],
    ];
  }, [routeData, origin, destination]);

  async function loadRoutes() {
    const response = await compareRoutes({
      origin,
      destination,
      time_of_day: timeOfDay,
    });
    setRouteData(response);
  }

  useEffect(() => {
    loadRoutes().catch((e) => setStatusMessage(e.message));
  }, [timeOfDay, origin, destination]);

  useEffect(() => {
    if (!trackingActive || !navigator.geolocation) return undefined;

    const watcher = navigator.geolocation.watchPosition(
      async (pos) => {
        const loc = { lat: pos.coords.latitude, lng: pos.coords.longitude };
        setCurrentLocation(loc);
        const moving = (pos.coords.speed || 0) > 0.3;
        if (moving) setInactivityAck(false);
        await updateTracking(userId, loc, moving);
        if (guardianEmail) {
          await shareGuardian({
            user_id: userId,
            guardian_email: guardianEmail,
            location: loc,
            destination_reached: false,
            inactivity_detected: false,
          });
        }
      },
      () => setStatusMessage("Location permission denied; using demo location."),
      { enableHighAccuracy: true, maximumAge: 5000, timeout: 12000 }
    );
    return () => navigator.geolocation.clearWatch(watcher);
  }, [trackingActive, guardianEmail, userId]);

  useEffect(() => {
    if (!trackingActive) return undefined;
    const t = setInterval(async () => {
      const res = await checkInactivity(userId);
      setInactivity(res);
      if (res.emergency_shared && !inactivityAck && !autoEscalated) {
        await triggerSOS({
          user_id: userId,
          location: currentLocation,
          timestamp: new Date().toISOString(),
          emergency_email: emergencyEmail,
          trigger_call: true,
        });
        await shareGuardian({
          user_id: userId,
          guardian_email: guardianEmail,
          location: currentLocation,
          destination_reached: false,
          inactivity_detected: true,
        });
        setAutoEscalated(true);
        setStatusMessage("No response after inactivity countdown. Emergency location shared.");
      }
    }, 10000);
    return () => clearInterval(t);
  }, [trackingActive, userId, guardianEmail, currentLocation, inactivityAck, autoEscalated, emergencyEmail]);

  async function handleStartTracking() {
    await startTracking(userId);
    const guardianResp = await shareGuardian({
      user_id: userId,
      guardian_email: guardianEmail,
      location: origin,
      tracking_started: true,
      destination_reached: false,
      inactivity_detected: false,
      origin,
      destination,
    });
    setTrackingActive(true);
    setAutoEscalated(false);
    if (guardianResp.email_sent) {
      setStatusMessage(`Smart tracking started. Email sent to guardian (${guardianEmail}).`);
    } else {
      setStatusMessage(
        guardianResp.email_error || "Tracking started, but guardian email could not be sent."
      );
    }
  }

  async function handleSOS() {
    let liveLocation = currentLocation;
    if (navigator.geolocation) {
      try {
        liveLocation = await new Promise((resolve, reject) => {
          navigator.geolocation.getCurrentPosition(
            (pos) => resolve({ lat: pos.coords.latitude, lng: pos.coords.longitude }),
            reject,
            { enableHighAccuracy: true, timeout: 12000 }
          );
        });
      } catch (_) {
        // Keep last known location if fresh location retrieval fails.
      }
    }
    setCurrentLocation(liveLocation);
    const response = await triggerSOS({
      user_id: userId,
      location: liveLocation,
      timestamp: new Date().toISOString(),
      emergency_email: emergencyEmail,
      trigger_call: true,
    });
    if (response.sent) {
      setStatusMessage(`SOS email sent to ${emergencyEmail}: ${response.location_link}`);
    } else {
      setStatusMessage(response.email_error || "SOS triggered, but email could not be sent.");
    }
  }

  async function markReachedDestination() {
    const response = await shareGuardian({
      user_id: userId,
      guardian_email: guardianEmail,
      location: destination,
      tracking_started: false,
      destination_reached: true,
      inactivity_detected: false,
      origin,
      destination,
    });
    if (response.email_sent) {
      setStatusMessage(`Destination reached email sent to guardian (${guardianEmail}).`);
    } else {
      setStatusMessage(
        response.email_error || "Reached destination recorded, but guardian email was not sent."
      );
    }
  }

  function coordInput(stateSetter, value, label) {
    return (
      <label className="coord">
        <span>{label}</span>
        <input
          type="text"
          value={`${value.lat},${value.lng}`}
          onChange={(e) => {
            const [latRaw, lngRaw] = e.target.value.split(",");
            const lat = Number((latRaw || "").trim());
            const lng = Number((lngRaw || "").trim());
            if (!Number.isNaN(lat) && !Number.isNaN(lng)) stateSetter({ lat, lng });
          }}
        />
      </label>
    );
  }

  return (
    <div className="app">
      <header>
        <h1>Smart Road Safety System</h1>
        <p>Safety score + safest route + live guardian tracking + SOS</p>
      </header>

      <section className="controls">
        <label>
          Time of day
          <select value={timeOfDay} onChange={(e) => setTimeOfDay(e.target.value)}>
            <option value="day">Day</option>
            <option value="night">Night (higher risk)</option>
          </select>
        </label>
        {coordInput(setOrigin, origin, "Origin lat,lng")}
        {coordInput(setDestination, destination, "Destination lat,lng")}
        <button onClick={loadRoutes}>Refresh route options</button>
      </section>

      <section className="grid">
        <div className="panel">
          <h2>Route Comparison</h2>
          {routeData && (
            <>
              <div className="route-card safest">
                <h3>Safest Route</h3>
                <p>ETA: {routeData.safest.eta_minutes} min</p>
                <p>Distance: {routeData.safest.distance_km} km</p>
                <p>Safety: {routeData.safest.safety_score} ({badgeForScore(routeData.safest.safety_score)})</p>
              </div>
              <div className="route-card fastest">
                <h3>Fastest Route</h3>
                <p>ETA: {routeData.fastest.eta_minutes} min</p>
                <p>Distance: {routeData.fastest.distance_km} km</p>
                <p>Safety: {routeData.fastest.safety_score} ({badgeForScore(routeData.fastest.safety_score)})</p>
              </div>
            </>
          )}
        </div>

        <div className="panel">
          <h2>Tracking & Safety Actions</h2>
          <h3>Guardian Contact</h3>
          <label>
            Guardian email
            <input value={guardianEmail} onChange={(e) => setGuardianEmail(e.target.value)} />
          </label>
          <div className="actions">
            <button onClick={handleStartTracking} disabled={trackingActive}>
              {trackingActive ? "Tracking Active" : "Start Smart Tracking"}
            </button>
            <button onClick={markReachedDestination}>Reached destination</button>
          </div>
          <h3>Emergency Contact</h3>
          <label>
            Emergency email
            <input value={emergencyEmail} onChange={(e) => setEmergencyEmail(e.target.value)} />
          </label>
          <div className="actions">
            <button className="sos" onClick={handleSOS}>
              Emergency SOS
            </button>
          </div>
          {inactivity?.send_alert && (
            <div className="alert">
              <strong>Inactivity detected</strong>
              <p>No movement for {inactivity.seconds_inactive}s</p>
              <p>Countdown: {inactivity.countdown_seconds_left}s</p>
              <button onClick={() => setInactivityAck(true)}>I am safe</button>
            </div>
          )}
          {statusMessage && <p className="status">{statusMessage}</p>}
        </div>
      </section>

      <section className="map-wrap">
        <MapContainer center={mapCenter} zoom={13} style={{ height: "440px", width: "100%" }}>
          <MapAutoFocus points={routeFocusPoints} />
          <TileLayer url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png" />
          {routeData?.fastest?.polyline && (
            <Polyline
              positions={routeData.fastest.polyline.map((p) => [p.lat, p.lng])}
              pathOptions={{ color: "#2f6fed", weight: 4, dashArray: "8" }}
            />
          )}
          {routeData?.safest?.polyline && (
            <Polyline
              positions={routeData.safest.polyline.map((p) => [p.lat, p.lng])}
              pathOptions={{ color: "#00a36c", weight: 4 }}
            />
          )}
          <Marker position={[origin.lat, origin.lng]}>
            <Popup>Origin</Popup>
          </Marker>
          <Marker position={[destination.lat, destination.lng]}>
            <Popup>Destination</Popup>
          </Marker>
        </MapContainer>
      </section>
    </div>
  );
}
