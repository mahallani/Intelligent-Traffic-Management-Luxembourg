"use client";
// Paramètres (2026-11-03): profile, password change, session; account management for administrators.
// All checks are repeated by the backend (app/backend/auth.py).
import { useCallback, useEffect, useState } from "react";
import { getJSON, postJSON } from "@/components/api";
import Icon from "@/components/icons";
import { useAuth } from "@/components/session";
import { initials } from "@/components/traffic";
import { Badge, Card, Notice, PageHeader } from "@/components/ui";

const ROLE_HELP = { admin: "Tous les droits, section technique et gestion des comptes", operator: "Lance, met en pause et arrête les simulations",
  analyst: "Consultation : supervision, rapports, prévisions, explications" };

function PasswordForm() {
  const [f, setF] = useState({ current: "", new: "", confirm: "" });
  const [msg, setMsg] = useState(null);
  const [busy, setBusy] = useState(false);
  const submit = async (e) => {
    e.preventDefault();
    setMsg(null);
    if (!f.current || !f.new) return setMsg(["bad", "Remplissez tous les champs."]);
    if (f.new.length < 10) return setMsg(["bad", "Le nouveau mot de passe doit contenir au moins 10 caractères."]);
    if (f.new !== f.confirm) return setMsg(["bad", "La confirmation ne correspond pas au nouveau mot de passe."]);
    setBusy(true);
    try {
      await postJSON("/auth/password", { current: f.current, new: f.new });
      setF({ current: "", new: "", confirm: "" });
      setMsg(["ok", "Mot de passe modifié. Vos autres sessions ont été fermées."]);
    } catch (err) { setMsg(["bad", err.message]); } finally { setBusy(false); }
  };
  const set = (k) => (e) => setF({ ...f, [k]: e.target.value });
  return (
    <form onSubmit={submit} noValidate>
      <div className="field"><label htmlFor="pw-cur">Mot de passe actuel</label><input id="pw-cur" type="password" autoComplete="current-password" value={f.current} onChange={set("current")} /></div>
      <div className="grid g-2" style={{ gap: ".8rem" }}>
        <div className="field"><label htmlFor="pw-new">Nouveau mot de passe</label><input id="pw-new" type="password" autoComplete="new-password" value={f.new} onChange={set("new")} />
          <span className="hint">10 caractères minimum, lettres et chiffres ou symboles.</span></div>
        <div className="field"><label htmlFor="pw-conf">Confirmation</label><input id="pw-conf" type="password" autoComplete="new-password" value={f.confirm} onChange={set("confirm")} /></div>
      </div>
      {msg && <div style={{ marginBottom: ".8rem" }}><Notice tone={msg[0]}>{msg[1]}</Notice></div>}
      <button className="btn btn-primary" type="submit" disabled={busy}>{busy && <span className="spinner" />}Changer le mot de passe</button>
    </form>
  );
}

function Users({ me }) {
  const [list, setList] = useState(null);
  const [roles, setRoles] = useState({});
  const [f, setF] = useState({ email: "", name: "", role: "analyst", password: "" });
  const [msg, setMsg] = useState(null);
  const [reset, setReset] = useState({});
  const load = useCallback(() => getJSON("/auth/users").then((r) => { setList(r.users); setRoles(r.roles); }).catch((e) => setMsg(["bad", e.message])), []);
  useEffect(() => { load(); }, [load]);
  const run = async (fn, ok) => {
    setMsg(null);
    try { await fn(); setMsg(["ok", ok]); load(); return true; } catch (e) { setMsg(["bad", e.message]); return false; }
  };
  const create = (e) => {
    e.preventDefault();
    run(() => postJSON("/auth/users", f), `Compte créé pour ${f.email}.`).then((ok) => ok && setF({ email: "", name: "", role: "analyst", password: "" }));
  };
  const set = (k) => (e) => setF({ ...f, [k]: e.target.value });
  return (
    <Card title="Comptes utilisateurs" icon="users" subtitle="Réservé aux administrateurs">
      {msg && <div style={{ marginBottom: ".8rem" }}><Notice tone={msg[0]}>{msg[1]}</Notice></div>}
      <div className="table-wrap">
        <table>
          <thead><tr><th>Utilisateur</th><th>Rôle</th><th>Statut</th><th>Actions</th></tr></thead>
          <tbody>{(list || []).map((u) => (
            <tr key={u.email}>
              <td><span className="cell-main">{u.name}</span><span className="cell-sub">{u.email}</span></td>
              <td>{u.role_label}</td>
              <td>{u.disabled ? <Badge tone="neutral">Désactivé</Badge> : <Badge tone="ok" dot>Actif</Badge>}</td>
              <td>
                <div className="row" style={{ gap: ".4rem" }}>
                  <input type="password" aria-label={`Nouveau mot de passe pour ${u.email}`} placeholder="Nouveau mot de passe" autoComplete="new-password"
                    value={reset[u.email] || ""} onChange={(e) => setReset({ ...reset, [u.email]: e.target.value })} style={{ width: "12rem", height: 32 }} />
                  <button className="btn btn-sm" type="button" disabled={!reset[u.email]}
                    onClick={() => run(() => postJSON(`/auth/users/${encodeURIComponent(u.email)}/password`, { password: reset[u.email] }), `Mot de passe réinitialisé pour ${u.email}.`).then((ok) => ok && setReset({ ...reset, [u.email]: "" }))}>Réinitialiser</button>
                  {u.email !== me.email && (
                    <button className={`btn btn-sm ${u.disabled ? "" : "btn-danger"}`} type="button"
                      onClick={() => run(() => postJSON(`/auth/users/${encodeURIComponent(u.email)}/status`, { disabled: !u.disabled }), u.disabled ? "Compte réactivé." : "Compte désactivé.")}>
                      {u.disabled ? "Réactiver" : "Désactiver"}</button>)}
                </div>
              </td>
            </tr>))}</tbody>
        </table>
      </div>
      <h3 style={{ marginTop: "1.2rem" }}>Créer un compte</h3>
      <form onSubmit={create} className="grid g-2" style={{ gap: "0 .8rem" }} noValidate>
        <div className="field"><label htmlFor="nu-name">Nom</label><input id="nu-name" value={f.name} onChange={set("name")} autoComplete="off" /></div>
        <div className="field"><label htmlFor="nu-mail">Adresse e-mail</label><input id="nu-mail" type="email" value={f.email} onChange={set("email")} autoComplete="off" /></div>
        <div className="field"><label htmlFor="nu-role">Rôle</label>
          <select id="nu-role" value={f.role} onChange={set("role")}>{Object.entries(roles).map(([k, l]) => <option key={k} value={k}>{l}</option>)}</select>
          <span className="hint">{ROLE_HELP[f.role]}</span></div>
        <div className="field"><label htmlFor="nu-pw">Mot de passe initial</label><input id="nu-pw" type="password" value={f.password} onChange={set("password")} autoComplete="new-password" />
          <span className="hint">À communiquer de façon sûre ; l'utilisateur le changera à sa première connexion.</span></div>
        <div><button className="btn btn-primary" type="submit"><Icon name="user" size={16} />Créer le compte</button></div>
      </form>
    </Card>
  );
}

export default function Parametres() {
  const { me, user, logout } = useAuth();
  if (!user) return null;
  return (
    <div className="stack">
      <PageHeader eyebrow="Compte" title="Paramètres" subtitle="Profil, sécurité du compte et gestion des accès." />
      {!me.auth_enabled && <Notice tone="warn" title="Authentification désactivée sur ce serveur (mode local).">Tout le monde a les droits d'administrateur. À n'utiliser qu'en développement.</Notice>}
      <div className="grid g-2">
        <Card title="Profil" icon="user">
          <div className="row" style={{ gap: "1rem" }}>
            <span className="avatar" style={{ width: 56, height: 56, fontSize: "1.1rem", borderRadius: 14 }}>{initials(user.name)}</span>
            <div><div style={{ fontWeight: 700, fontSize: "1.1rem" }}>{user.name}</div><div className="muted">{user.email}</div>
              <div style={{ marginTop: ".3rem" }}><Badge tone="info">{user.role_label}</Badge></div></div>
          </div>
          <p className="hint" style={{ marginTop: "1rem" }}>{ROLE_HELP[user.role]}.</p>
          {me.auth_enabled && <button className="btn" type="button" onClick={logout}><Icon name="logout" size={16} />Se déconnecter</button>}
        </Card>
        {me.auth_enabled && <Card title="Mot de passe" icon="lock"><PasswordForm /></Card>}
      </div>
      {me.auth_enabled && user.role === "admin" && <Users me={user} />}
      <Card title="Sécurité de la session" icon="shield">
        <ul className="small" style={{ margin: 0, paddingLeft: "1.1rem", color: "var(--ink-2)" }}>
          <li>Session gérée par le serveur, dans un cookie inaccessible aux scripts de la page ; fermeture après 2 h d'inactivité et au plus tard après 12 h.</li>
          <li>Après 5 essais de connexion incorrects, nouvel essai possible seulement 5 minutes plus tard.</li>
          <li>Mots de passe conservés uniquement sous forme d'empreinte (scrypt), jamais en clair.</li>
        </ul>
      </Card>
    </div>
  );
}
