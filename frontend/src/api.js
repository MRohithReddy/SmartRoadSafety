const API_BASE = import.meta.env.VITE_API_BASE_URL || "http://localhost:8000";

//random comment on frontend
async function post(path, payload) {
  const response = await fetch(`${API_BASE}${path}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  if (!response.ok) {
    throw new Error(`API ${path} failed: ${response.status}`);
  }
  return response.json();
}

export function fetchRoadSafety(time_of_day, traffic_density) {
  return post("/roads/safety", { time_of_day, traffic_density });
}

export function compareRoutes(payload) {
  return post("/routes/compare", payload);
}

export function startTracking(user_id) {
  return post("/tracking/start", {
    user_id,
    started_at: new Date().toISOString(),
  });
}

export function updateTracking(user_id, location, moving) {
  return post("/tracking/update", {
    user_id,
    location,
    moving,
    timestamp: new Date().toISOString(),
  });
}

export function checkInactivity(user_id) {
  return post("/tracking/check-inactivity", {
    user_id,
    now: new Date().toISOString(),
  });
}

export function triggerSOS(payload) {
  return post("/sos/trigger", payload);
}

export function shareGuardian(payload) {
  return post("/guardian/share", payload);
}
