"use client";
// Session and live-simulation contexts (2026-11-03).
//   AuthProvider: who is connected (GET /api/auth/me) and what the role allows. The backend enforces the same rules:
//                 hiding a button here is comfort, not security.
//   SimProvider : one shared polling of GET /api/sim/state (1 s while a simulation is active, 4 s otherwise) and the
//                 network geometry (GET /api/network), so every page shows the same live data.
import { createContext, useCallback, useContext, useEffect, useRef, useState } from "react";
import { getJSON, postJSON } from "./api";
import { ACTIVE } from "./traffic";

const AuthCtx = createContext(null);
const SimCtx = createContext(null);

const PERMS = { simulate: ["admin", "operator"], admin: ["admin"] };

export function AuthProvider({ children }) {
  const [me, setMe] = useState(null);
  const [error, setError] = useState(null);
  const load = useCallback(() => getJSON("/auth/me").then((m) => { setMe(m); setError(null); return m; })
    .catch((e) => { setError(e); return null; }), []);
  useEffect(() => { load(); }, [load]);
  const user = me?.authenticated ? me.user : null;
  const can = useCallback((perm) => !!user && (PERMS[perm] || []).includes(user.role), [user]);
  const logout = useCallback(async () => {
    try { await postJSON("/auth/logout"); } catch { /* already logged out */ }
    window.location.assign("/login/");
  }, []);
  return <AuthCtx.Provider value={{ me, user, error, can, logout, reload: load }}>{children}</AuthCtx.Provider>;
}

export const useAuth = () => useContext(AuthCtx);

export function SimProvider({ children }) {
  const [state, setState] = useState(null);
  const [net, setNet] = useState(null);
  const [conn, setConn] = useState("checking");
  const [updated, setUpdated] = useState(null);
  const timer = useRef(null);
  const active = ACTIVE.includes(state?.status);

  const poll = useCallback(() => getJSON("/sim/state")
    .then((s) => { setState(s); setConn("ok"); setUpdated(Date.now()); return s; })
    .catch((e) => { if (e.network || e.status >= 500) setConn("down"); return null; }), []);

  useEffect(() => {
    getJSON("/network").then(setNet).catch(() => {});
  }, []);
  useEffect(() => {
    poll();
    timer.current = setInterval(() => { if (!document.hidden) poll(); }, active ? 1000 : 4000);
    return () => clearInterval(timer.current);
  }, [poll, active]);

  return <SimCtx.Provider value={{ state, net, conn, updated, refresh: poll, setState, active }}>{children}</SimCtx.Provider>;
}

export const useSim = () => useContext(SimCtx);
