"use client";
// Login page (2026-11-03). The password is sent once to POST /api/auth/login (same origin); the backend answers with an
// HttpOnly session cookie. Nothing is stored by this page (no localStorage, no sessionStorage).
import { useEffect, useState } from "react";
import { postJSON } from "@/components/api";
import Icon, { Logo } from "@/components/icons";
import { useAuth } from "@/components/session";
import { Notice } from "@/components/ui";

const EMAIL = /^[^@\s]+@[^@\s]+\.[^@\s]{2,}$/;

function safeNext(raw) {
  // only a path of this site (never another host): "/xxx" but not "//host" nor "/login"
  if (!raw || !raw.startsWith("/") || raw.startsWith("//") || raw.startsWith("/\\") || raw.startsWith("/login")) return "/";
  return raw;
}

function NetworkArt() {
  // decorative road network (abstract, not the real map)
  const roads = ["M-20 520 L380 330 L760 180 L1100 40", "M120 -20 L260 300 L330 640", "M520 -20 L560 250 L700 700",
    "M-20 260 L300 300 L620 420 L1100 560", "M820 -20 L760 180 L900 700"];
  const nodes = [[380, 330], [560, 250], [760, 180], [300, 300], [620, 420]];
  return (
    <svg className="net" viewBox="0 0 1000 680" preserveAspectRatio="xMidYMid slice" aria-hidden="true">
      {roads.map((d, i) => <path key={i} d={d} fill="none" stroke="#2B4A72" strokeWidth={i === 0 ? 10 : 6} strokeLinecap="round" />)}
      {roads.map((d, i) => <path key={`c${i}`} d={d} fill="none" stroke="#26B6D4" strokeOpacity=".35" strokeWidth="1.2" strokeDasharray="2 14" />)}
      {nodes.map(([x, y], i) => (
        <g key={i}><circle cx={x} cy={y} r="16" fill="#101D2E" stroke="#2478E5" strokeWidth="2" />
          <circle cx={x} cy={y} r="5" fill={["#22A06B", "#F59E0B", "#E5484D", "#22A06B", "#26B6D4"][i]} /></g>))}
    </svg>
  );
}

export default function Login() {
  const { me } = useAuth();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [show, setShow] = useState(false);
  const [errors, setErrors] = useState({});
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [forgot, setForgot] = useState(false);
  const [next, setNext] = useState("/");
  const [expired, setExpired] = useState(false);

  useEffect(() => {
    const q = new URLSearchParams(window.location.search);
    setNext(safeNext(q.get("next")));
    setExpired(q.get("expired") === "1");
  }, []);
  useEffect(() => {      // already connected (or authentication disabled): go to the application
    if (me && me.authenticated) window.location.replace(next);
  }, [me, next]);

  const validate = () => {
    const e = {};
    if (!email.trim()) e.email = "Saisissez votre adresse e-mail.";
    else if (!EMAIL.test(email.trim())) e.email = "Adresse e-mail invalide.";
    if (!password) e.password = "Saisissez votre mot de passe.";
    setErrors(e);
    return !Object.keys(e).length;
  };

  const submit = async (ev) => {
    ev.preventDefault();
    setError("");
    if (!validate()) return;
    setBusy(true);
    try {
      await postJSON("/auth/login", { email: email.trim(), password });
      setPassword("");
      window.location.replace(next);
    } catch (e) {
      setError(e.network ? "Le serveur ne répond pas. Vérifiez votre connexion ou contactez l'administrateur." : e.message);
      setBusy(false);
    }
  };

  return (
    <div className="login">
      <section className="login-art" aria-hidden="false">
        <NetworkArt />
        <div className="login-brand"><Logo size={40} /><div><strong>Intelligent Traffic Management</strong><span>Luxembourg</span></div></div>
        <div className="login-pitch">
          <h2>Supervision et pilotage intelligent des feux de circulation.</h2>
          <p>Suivi du trafic carrefour par carrefour, agents de décision, prévisions et décisions explicables, sur une même plateforme.</p>
          <div className="login-points">
            <div><span className="ic"><Icon name="monitor" size={18} /></span>Supervision en temps réel des carrefours</div>
            <div><span className="ic"><Icon name="forecast" size={18} /></span>Prévisions de trafic à 5, 10 et 15 minutes</div>
            <div><span className="ic"><Icon name="xai" size={18} /></span>Chaque décision de l'IA expliquée</div>
          </div>
        </div>
        <div className="login-legal">Kirchberg · avenue J.F. Kennedy · environnement de simulation</div>
      </section>

      <section className="login-form-side">
        <div className="login-card">
          <div className="login-mobile-brand"><Logo size={34} /><strong>Intelligent Traffic Management</strong></div>
          <h1>Intelligent Traffic Management Luxembourg</h1>
          <p className="page-sub">Connectez-vous pour accéder à la plateforme.</p>

          {expired && <div style={{ marginBottom: "1rem" }}><Notice tone="warn" title="Session expirée.">Reconnectez-vous pour continuer.</Notice></div>}
          {me && me.auth_enabled && me.setup_required && (
            <div style={{ marginBottom: "1rem" }}>
              <Notice tone="info" title="Aucun compte n'est encore configuré.">
                L'administrateur doit créer le premier compte sur le serveur :
                {" "}<code>python -m app.backend.auth add-user --email … --name … --role admin</code>
              </Notice>
            </div>)}

          <form onSubmit={submit} noValidate>
            <div className="field">
              <label htmlFor="email">Adresse e-mail</label>
              <div className="input-ic">
                <Icon name="mail" size={17} />
                <input id="email" type="email" autoComplete="username" value={email} onChange={(e) => setEmail(e.target.value)}
                  className={errors.email ? "input-error" : ""} aria-invalid={!!errors.email} aria-describedby={errors.email ? "email-err" : undefined}
                  placeholder="prenom.nom@organisation.lu" autoFocus />
              </div>
              {errors.email && <span className="field-error" id="email-err">{errors.email}</span>}
            </div>
            <div className="field">
              <div className="row" style={{ justifyContent: "space-between" }}>
                <label htmlFor="password" className="field-label">Mot de passe</label>
                <button type="button" className="link-btn" onClick={() => setForgot(!forgot)} aria-expanded={forgot}>Mot de passe oublié ?</button>
              </div>
              <div className="pw-wrap input-ic">
                <Icon name="lock" size={17} />
                <input id="password" type={show ? "text" : "password"} autoComplete="current-password" value={password}
                  onChange={(e) => setPassword(e.target.value)} className={errors.password ? "input-error" : ""}
                  aria-invalid={!!errors.password} aria-describedby={errors.password ? "pw-err" : undefined} />
                <button type="button" className="pw-toggle" onClick={() => setShow(!show)} aria-label={show ? "Masquer le mot de passe" : "Afficher le mot de passe"}
                  aria-pressed={show}>
                  <Icon name={show ? "eyeOff" : "eye"} size={18} />
                </button>
              </div>
              {errors.password && <span className="field-error" id="pw-err">{errors.password}</span>}
            </div>
            {forgot && (
              <div style={{ marginBottom: "1rem" }}>
                <Notice tone="info" title="Réinitialisation du mot de passe.">
                  Pour des raisons de sécurité, la réinitialisation est faite par l'administrateur de la plateforme de votre organisation.
                  Contactez-le : il vous attribuera un nouveau mot de passe, à changer dès votre connexion (Paramètres).
                </Notice>
              </div>)}
            {error && <div style={{ marginBottom: "1rem" }}><Notice tone="bad">{error}</Notice></div>}
            <button className="btn btn-primary btn-lg btn-block" type="submit" disabled={busy || (me && !me.auth_enabled)}>
              {busy ? <><span className="spinner" aria-hidden="true" />Connexion…</> : "Se connecter"}
            </button>
          </form>
          {me && !me.auth_enabled && (
            <div style={{ marginTop: "1rem" }}><Notice tone="warn">Authentification désactivée sur ce serveur (mode local) : <a href="/">ouvrir l'application</a>.</Notice></div>)}
          <p className="hint" style={{ marginTop: "1.2rem", textAlign: "center" }}>
            <Icon name="shield" size={14} /> Session protégée, gérée par le serveur de la plateforme.
          </p>
        </div>
      </section>
    </div>
  );
}
