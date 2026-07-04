/**
 * Thin wrapper around the backend's REST API.
 * In development, Vite proxies /api -> the FastAPI backend (see vite.config.js).
 * In production (docker-compose), the frontend is served by nginx which
 * proxies /api the same way (see frontend/nginx.conf).
 */
const BASE = "/api";

async function request(path, options = {}) {
  const res = await fetch(`${BASE}${path}`, {
    headers: { "Content-Type": "application/json" },
    ...options,
  });

  if (!res.ok) {
    let detail = res.statusText;
    try {
      const body = await res.json();
      detail = body.detail || detail;
    } catch {
      /* response wasn't JSON */
    }
    throw new Error(detail);
  }
  return res.json();
}

export function geocode(query, limit = 5) {
  return request("/geocode", { method: "POST", body: JSON.stringify({ query, limit }) });
}

export function optimizeRoute(payload) {
  return request("/optimize", { method: "POST", body: JSON.stringify(payload) });
}
