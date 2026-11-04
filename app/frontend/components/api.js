// Same origin when served by the Python backend; during `npm run dev` the backend runs on port 8000
// (authentication cookies are only sent to the same origin: use the built application on port 8000 when auth is on).
export const API =
  typeof window !== "undefined" && window.location.port === "3000" ? "http://127.0.0.1:8000/api" : "/api";

export class ApiError extends Error {
  constructor(message, status, detail) {
    super(message);
    this.status = status;
    this.detail = detail;
  }
}

function sessionExpired(path) {
  // 2026-11-03: a 401 outside /auth/* means the session ended -> back to the login page (the backend redirects too)
  if (typeof window === "undefined" || path.startsWith("/auth/") || window.location.pathname.startsWith("/login")) return;
  const next = encodeURIComponent(window.location.pathname + window.location.search);
  window.location.assign(`/login/?expired=1&next=${next}`);
}

async function request(path, init) {
  let r;
  try {
    r = await fetch(`${API}${path}`, { cache: "no-store", credentials: "same-origin", ...init });
  } catch {
    const e = new ApiError("Serveur injoignable", 0);
    e.network = true;
    throw e;
  }
  const body = await r.json().catch(() => ({}));
  if (!r.ok) {
    if (r.status === 401) sessionExpired(path);
    const d = body.detail;
    throw new ApiError(typeof d === "string" ? d : d?.message || `HTTP ${r.status}`, r.status, d);
  }
  return body;
}

export const getJSON = (path) => request(path);

export const postJSON = (path, data) =>
  request(path, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(data || {}) });

export const fmt = (v, d = 1) =>
  v === null || v === undefined || Number.isNaN(v) ? "–" : Number(v).toLocaleString("fr-FR", { maximumFractionDigits: d, minimumFractionDigits: 0 });
