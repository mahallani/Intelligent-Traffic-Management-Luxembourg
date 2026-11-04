"use client";
// Application frame (2026-11-03): retractable sidebar, top bar (status, notifications, user menu), route guard.
// The guard here only decides what to DISPLAY; the backend refuses every API call and page without a valid session.
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useEffect, useRef, useState } from "react";
import Icon, { Logo } from "./icons";
import { AuthProvider, SimProvider, useAuth, useSim } from "./session";
import { STATUS, alertType, initials, junction } from "./traffic";
import { Spinner } from "./ui";

const NAV = [
  ["Exploitation", [
    ["/", "Vue d'ensemble", "overview"],
    ["/supervision/", "Supervision du trafic", "monitor"],
    ["/simulation/", "Simulation", "play"],
    ["/carrefours/", "Carrefours", "signal"],
  ]],
  ["Analyse", [
    ["/previsions/", "Prévisions IA", "forecast"],
    ["/incidents/", "Incidents et alertes", "alert"],
    ["/xai/", "IA explicable", "xai"],
    ["/rapports/", "Rapports", "report"],
  ]],
  ["Système", [
    ["/parametres/", "Paramètres", "settings"],
    ["/technique/", "Section technique", "tool", "admin"],
  ]],
];
const ALL = NAV.flatMap(([, items]) => items);
const norm = (p) => (p.endsWith("/") ? p : `${p}/`);
const isActive = (path, href) => (href === "/" ? norm(path) === "/" : norm(path).startsWith(href));
const ADMIN_ONLY = ["/technique/"];

function readPref(key, fallback) {
  try { const v = window.localStorage.getItem(key); return v === null ? fallback : v === "1"; } catch { return fallback; }
}
function writePref(key, v) {
  try { window.localStorage.setItem(key, v ? "1" : "0"); } catch { /* storage unavailable: ignore */ }
}

function useOutside(ref, onOut) {
  useEffect(() => {
    const h = (e) => { if (ref.current && !ref.current.contains(e.target)) onOut(); };
    const k = (e) => { if (e.key === "Escape") onOut(); };
    document.addEventListener("mousedown", h);
    document.addEventListener("keydown", k);
    return () => { document.removeEventListener("mousedown", h); document.removeEventListener("keydown", k); };
  }, [ref, onOut]);
}

function Sidebar({ collapsed, onToggle, mobileOpen, onClose }) {
  const path = usePathname();
  const { user } = useAuth();
  const { state } = useSim();
  const active = (state?.alerts || []).filter((a) => !a.end_clock).length;
  return (
    <aside className={`sidebar ${collapsed ? "collapsed" : ""} ${mobileOpen ? "open" : ""}`} aria-label="Navigation">
      <div className="sb-brand">
        <Logo size={34} />
        <div className="sb-brand-text"><strong>Intelligent Traffic</strong><span>Management Luxembourg</span></div>
        <button className="sb-close icon-btn" type="button" onClick={onClose} aria-label="Fermer le menu"><Icon name="close" /></button>
      </div>
      <nav className="sb-nav" aria-label="Navigation principale">
        {NAV.map(([group, items]) => {
          const shown = items.filter((it) => !it[3] || user?.role === it[3]);
          if (!shown.length) return null;
          return (
            <div className="sb-group" key={group}>
              <div className="sb-group-label">{group}</div>
              {shown.map(([href, label, icon]) => (
                <Link key={href} href={href} className="sb-link" aria-current={isActive(path, href) ? "page" : undefined}
                  title={collapsed ? label : undefined} onClick={onClose}>
                  <Icon name={icon} size={19} />
                  <span className="sb-label">{label}</span>
                  {href === "/incidents/" && active > 0 && <span className="sb-count" aria-label={`${active} alerte(s) en cours`}>{active}</span>}
                </Link>
              ))}
            </div>
          );
        })}
      </nav>
      <div className="sb-foot">
        <div className="sb-site"><Icon name="pin" size={16} /><span>Kirchberg · Av. J.F. Kennedy<br /><small>4 carrefours · données de simulation</small></span></div>
        <button type="button" className="sb-collapse" onClick={onToggle} aria-label={collapsed ? "Déplier le menu" : "Replier le menu"}>
          <Icon name={collapsed ? "chevronRight" : "chevronLeft"} size={18} /><span className="sb-label">Replier</span>
        </button>
      </div>
    </aside>
  );
}

function SystemStatus() {
  const { state, conn } = useSim();
  const st = STATUS[state?.status] || STATUS.idle;
  if (conn === "down") return <span className="sys-pill tone-bad"><span className="pulse-dot" />Serveur injoignable</span>;
  return (
    <span className={`sys-pill tone-${st.tone}`} title="État du serveur et de la simulation">
      <span className={`pulse-dot ${state?.status === "running" ? "live" : ""}`} />
      <span className="sys-pill-text">{st.label}</span>
      {state && state.status !== "idle" && state.clock && <span className="sys-clock">{state.clock}</span>}
    </span>
  );
}

function Notifications() {
  const [open, setOpen] = useState(false);
  const ref = useRef(null);
  useOutside(ref, () => setOpen(false));
  const { state } = useSim();
  const alerts = (state?.alerts || []).filter((a) => !a.end_clock);
  const amb = state?.emergency_live;
  const items = [
    ...alerts.map((a) => ({ k: `a${a.clock}${a.lane}`, tone: "bad", title: alertType(a.rule).label, sub: `${junction(a.tls)} · depuis ${a.clock}` })),
    ...(amb && amb.status === "en circulation" ? [{ k: "amb", tone: "sim", title: "Ambulance en circulation", sub: amb.next ? `vers ${amb.next.label}` : "sortie de l'avenue" }] : []),
  ];
  return (
    <div className="menu-wrap" ref={ref}>
      <button type="button" className="icon-btn" aria-label={`Notifications (${items.length})`} aria-expanded={open} onClick={() => setOpen(!open)}>
        <Icon name="bell" />
        {items.length > 0 && <span className="notif-dot">{items.length}</span>}
      </button>
      {open && (
        <div className="menu menu-wide" role="dialog" aria-label="Notifications">
          <div className="menu-head">Notifications</div>
          {items.length === 0 && <p className="menu-empty">Aucune alerte en cours.</p>}
          {items.map((it) => (
            <div key={it.k} className="menu-item static"><span className={`dot-tone tone-${it.tone}`} /><div><strong>{it.title}</strong><small>{it.sub}</small></div></div>
          ))}
          <Link className="menu-foot" href="/incidents/" onClick={() => setOpen(false)}>Voir les incidents et alertes</Link>
        </div>
      )}
    </div>
  );
}

function UserMenu() {
  const [open, setOpen] = useState(false);
  const ref = useRef(null);
  useOutside(ref, () => setOpen(false));
  const { user, me, logout } = useAuth();
  if (!user) return null;
  return (
    <div className="menu-wrap" ref={ref}>
      <button type="button" className="user-btn" aria-expanded={open} aria-haspopup="menu" onClick={() => setOpen(!open)}>
        <span className="avatar">{initials(user.name)}</span>
        <span className="user-text"><strong>{user.name}</strong><small>{user.role_label}</small></span>
        <Icon name="chevronDown" size={16} />
      </button>
      {open && (
        <div className="menu" role="menu">
          <div className="menu-head"><strong>{user.name}</strong><small>{user.email}</small></div>
          <Link role="menuitem" className="menu-item" href="/parametres/" onClick={() => setOpen(false)}><Icon name="user" size={17} />Profil et sécurité</Link>
          {me?.auth_enabled
            ? <button role="menuitem" type="button" className="menu-item" onClick={logout}><Icon name="logout" size={17} />Se déconnecter</button>
            : <p className="menu-empty">Authentification désactivée sur ce serveur (mode local).</p>}
        </div>
      )}
    </div>
  );
}

function Topbar({ onMenu }) {
  const path = usePathname();
  const cur = ALL.find(([href]) => isActive(path, href));
  return (
    <header className="topbar">
      <button type="button" className="icon-btn only-mobile" onClick={onMenu} aria-label="Ouvrir le menu"><Icon name="menu" /></button>
      <div className="tb-title">
        <span className="tb-platform">Intelligent Traffic Management Luxembourg</span>
        <span className="tb-page">{cur ? cur[1] : ""}</span>
      </div>
      <div className="tb-right">
        <SystemStatus />
        <Notifications />
        <UserMenu />
      </div>
    </header>
  );
}

function Guard({ children }) {
  const { me, user, error, reload } = useAuth();
  const router = useRouter();
  const path = usePathname();
  const needLogin = me && me.auth_enabled && !me.authenticated;
  useEffect(() => {
    if (needLogin) router.replace(`/login/?next=${encodeURIComponent(path)}`);
  }, [needLogin, path, router]);
  if (error && !me) {
    return (
      <div className="splash">
        <Logo size={44} />
        <strong>Le serveur de l'application ne répond pas.</strong>
        <p>Vérifiez que le serveur est démarré, puis réessayez.</p>
        <button className="btn btn-primary" type="button" onClick={reload}><Icon name="refresh" size={16} />Réessayer</button>
      </div>
    );
  }
  if (!me || needLogin) return <div className="splash"><Logo size={44} /><Spinner label="Vérification de la session…" /></div>;
  if (ADMIN_ONLY.some((p) => norm(path).startsWith(p)) && user?.role !== "admin") {
    return <div className="splash"><Icon name="lock" size={28} /><strong>Accès réservé aux administrateurs.</strong><Link className="btn btn-secondary" href="/">Retour à la vue d'ensemble</Link></div>;
  }
  return children;
}

function Frame({ children }) {
  const [collapsed, setCollapsed] = useState(false);
  const [mobileOpen, setMobileOpen] = useState(false);
  useEffect(() => { setCollapsed(readPref("itm.sidebar.collapsed", false)); }, []);
  const toggle = () => { setCollapsed((c) => { writePref("itm.sidebar.collapsed", !c); return !c; }); };
  return (
    <div className={`app ${collapsed ? "sb-collapsed" : ""}`}>
      <a className="skip" href="#contenu">Aller au contenu</a>
      <Sidebar collapsed={collapsed} onToggle={toggle} mobileOpen={mobileOpen} onClose={() => setMobileOpen(false)} />
      {mobileOpen && <div className="scrim" onClick={() => setMobileOpen(false)} aria-hidden="true" />}
      <div className="main-col">
        <Topbar onMenu={() => setMobileOpen(true)} />
        <main id="contenu" className="content">{children}</main>
      </div>
    </div>
  );
}

export default function AppShell({ children }) {
  const path = usePathname() || "/";
  if (path.startsWith("/login")) return <AuthProvider>{children}</AuthProvider>;
  return (
    <AuthProvider>
      <Guard>
        <SimProvider>
          <Frame>{children}</Frame>
        </SimProvider>
      </Guard>
    </AuthProvider>
  );
}
