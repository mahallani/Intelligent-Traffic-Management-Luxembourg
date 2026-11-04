"""Authentication of the control application (2026-11-03). Python standard library only, no new dependency.

What it does
  * Accounts in a local JSON file (default: <project>/config/users.json, override with ITM_USERS_FILE). The file is NOT
    served by the web server. Passwords are never stored: only a scrypt hash (random 16-byte salt, n=2**14, r=8, p=1).
  * Sessions kept in the backend memory. The browser only receives a random token in a cookie that JavaScript cannot
    read (HttpOnly) and that the browser never sends from another site (SameSite=Strict). Nothing goes to localStorage.
    Idle expiry 2 h, absolute expiry 12 h. Restarting the backend logs everybody out.
  * After 5 failed logins in 15 minutes for one e-mail address or one client address: refused for 5 minutes.
  * Requests that change something (POST/PUT/PATCH/DELETE) coming from another web origin are refused.
  * Three roles: admin (everything, technical section, accounts), operator (runs simulations), analyst (read only).

What it does NOT do yet (to be done before a real deployment)
  * HTTPS: the cookie gets the Secure flag only when the request arrives over HTTPS (or ITM_COOKIE_SECURE=1).
  * Persistent / shared sessions (several backend processes), audit log, password reset by e-mail, MFA.

Command line (from the project root):
    python -m app.backend.auth add-user --email admin@example.lu --name "Admin" --role admin
    python -m app.backend.auth set-password --email admin@example.lu
    python -m app.backend.auth list
    python -m app.backend.auth disable --email someone@example.lu      (enable: same with `enable`)
"""
from __future__ import annotations

import argparse
import base64
import hashlib
import hmac
import json
import os
import re
import secrets
import threading
import time
from collections import deque
from datetime import datetime
from pathlib import Path

from fastapi import APIRouter, HTTPException, Request, Response
from pydantic import BaseModel

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_USERS_FILE = ROOT / "config" / "users.json"
ROLES = ("admin", "operator", "analyst")
ROLE_LABELS = {"admin": "Administrateur", "operator": "Opérateur trafic", "analyst": "Analyste"}
COOKIE = "itm_session"
IDLE_S, ABSOLUTE_S = 2 * 3600, 12 * 3600
MAX_FAILURES, FAILURE_WINDOW_S, LOCK_S = 5, 15 * 60, 5 * 60
MIN_PASSWORD = 10
SCRYPT = {"n": 2 ** 14, "r": 8, "p": 1, "dklen": 32}
EMAIL_RE = re.compile(r"^[^@\s]{1,64}@[^@\s]{1,190}\.[^@\s]{2,24}$")


class AuthError(ValueError):
    """A request the user can correct (bad input, wrong password...). The message is shown as is (French)."""


# ------------------------------------------------------------------------------------------- passwords
def hash_password(password: str) -> dict:
    salt = secrets.token_bytes(16)
    digest = hashlib.scrypt(password.encode("utf-8"), salt=salt, maxmem=64 * 1024 * 1024, **SCRYPT)
    return {"alg": "scrypt", **{k: SCRYPT[k] for k in ("n", "r", "p")},
            "salt": base64.b64encode(salt).decode(), "hash": base64.b64encode(digest).decode()}


def verify_password(password: str, rec: dict) -> bool:
    try:
        salt, want = base64.b64decode(rec["salt"]), base64.b64decode(rec["hash"])
        got = hashlib.scrypt(password.encode("utf-8"), salt=salt, n=int(rec["n"]), r=int(rec["r"]), p=int(rec["p"]),
                             dklen=len(want), maxmem=64 * 1024 * 1024)
    except (KeyError, ValueError, TypeError):
        return False
    return hmac.compare_digest(got, want)


_DUMMY = None


def _dummy_check(password: str) -> None:
    """Same work as a real check when the e-mail is unknown (the answer time does not reveal which accounts exist)."""
    global _DUMMY
    if _DUMMY is None:
        _DUMMY = hash_password(secrets.token_hex(8))
    verify_password(password, _DUMMY)


def check_new_password(password: str) -> None:
    if not isinstance(password, str) or len(password) < MIN_PASSWORD:
        raise AuthError(f"Le mot de passe doit contenir au moins {MIN_PASSWORD} caractères.")
    if len(password) > 256:
        raise AuthError("Le mot de passe est trop long (256 caractères au plus).")
    if password.strip() != password or password.isdigit() or password.isalpha():
        raise AuthError("Le mot de passe doit mélanger lettres et chiffres ou symboles, sans espace au début ni à la fin.")


def normalize_email(email: str) -> str:
    e = (email or "").strip().lower()
    if not EMAIL_RE.match(e):
        raise AuthError("Adresse e-mail invalide.")
    return e


# ------------------------------------------------------------------------------------------- accounts
class UserStore:
    """Accounts file: {"users": [{email, name, role, disabled, created, password: {scrypt record}}]}."""

    def __init__(self, path: Path | str | None = None):
        self.path = Path(path or os.environ.get("ITM_USERS_FILE") or DEFAULT_USERS_FILE)
        self._lock = threading.Lock()

    def _read(self) -> list[dict]:
        if not self.path.exists():
            return []
        return json.loads(self.path.read_text(encoding="utf-8")).get("users", [])

    def _write(self, users: list[dict]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(json.dumps({"users": users}, ensure_ascii=False, indent=1), encoding="utf-8")
        os.replace(tmp, self.path)           # atomic: never a half-written accounts file

    @staticmethod
    def public(u: dict) -> dict:
        return {"email": u["email"], "name": u.get("name") or u["email"], "role": u["role"],
                "role_label": ROLE_LABELS.get(u["role"], u["role"]), "disabled": bool(u.get("disabled")),
                "created": u.get("created")}

    def count(self) -> int:
        with self._lock:
            return len(self._read())

    def list(self) -> list[dict]:
        with self._lock:
            return [self.public(u) for u in self._read()]

    def get(self, email: str) -> dict | None:
        e = (email or "").strip().lower()
        with self._lock:
            return next((u for u in self._read() if u["email"] == e), None)

    def add(self, email: str, name: str, role: str, password: str) -> dict:
        e = normalize_email(email)
        name = (name or "").strip()
        if not name or len(name) > 80:
            raise AuthError("Le nom est obligatoire (80 caractères au plus).")
        if role not in ROLES:
            raise AuthError(f"Rôle inconnu : {role}.")
        check_new_password(password)
        with self._lock:
            users = self._read()
            if any(u["email"] == e for u in users):
                raise AuthError("Un compte existe déjà avec cette adresse.")
            u = {"email": e, "name": name, "role": role, "disabled": False,
                 "created": datetime.now().isoformat(timespec="seconds"), "password": hash_password(password)}
            users.append(u)
            self._write(users)
            return self.public(u)

    def _update(self, email: str, fn) -> dict:
        e = (email or "").strip().lower()
        with self._lock:
            users = self._read()
            u = next((x for x in users if x["email"] == e), None)
            if u is None:
                raise AuthError("Compte introuvable.")
            fn(u)
            self._write(users)
            return self.public(u)

    def set_password(self, email: str, password: str) -> dict:
        check_new_password(password)
        rec = hash_password(password)
        return self._update(email, lambda u: u.update(password=rec))

    def set_disabled(self, email: str, disabled: bool) -> dict:
        return self._update(email, lambda u: u.update(disabled=bool(disabled)))

    def authenticate(self, email: str, password: str) -> dict | None:
        u = self.get(email)
        if u is None:
            _dummy_check(password or "")
            return None
        if not verify_password(password or "", u.get("password") or {}) or u.get("disabled"):
            return None
        return self.public(u)


# ------------------------------------------------------------------------------------------- sessions
class SessionStore:
    """token -> session. Only the SHA-256 of the token is kept (a memory dump does not give usable cookies)."""

    def __init__(self, idle_s: float = IDLE_S, absolute_s: float = ABSOLUTE_S, clock=time.time):
        self.idle_s, self.absolute_s, self.clock = idle_s, absolute_s, clock
        self._s: dict[str, dict] = {}
        self._lock = threading.Lock()

    @staticmethod
    def _key(token: str) -> str:
        return hashlib.sha256(token.encode()).hexdigest()

    def create(self, email: str) -> str:
        token = secrets.token_urlsafe(32)
        now = self.clock()
        with self._lock:
            self._s[self._key(token)] = {"email": email, "created": now, "last": now}
        return token

    def get(self, token: str | None) -> dict | None:
        if not token:
            return None
        k, now = self._key(token), self.clock()
        with self._lock:
            s = self._s.get(k)
            if s is None:
                return None
            if now - s["last"] > self.idle_s or now - s["created"] > self.absolute_s:
                del self._s[k]
                return None
            s["last"] = now
            return dict(s)

    def delete(self, token: str | None) -> None:
        if token:
            with self._lock:
                self._s.pop(self._key(token), None)

    def delete_user(self, email: str, keep: str | None = None) -> None:
        keep_k = self._key(keep) if keep else None
        with self._lock:
            for k in [k for k, s in self._s.items() if s["email"] == email and k != keep_k]:
                del self._s[k]


class LoginGuard:
    """Refuses logins for LOCK_S after MAX_FAILURES failures within FAILURE_WINDOW_S, per e-mail and per client."""

    def __init__(self, clock=time.time):
        self.clock = clock
        self._f: dict[str, deque] = {}
        self._lock = threading.Lock()

    def locked_for(self, *keys: str) -> int:
        now = self.clock()
        with self._lock:
            wait = 0
            for k in keys:
                q = self._f.get(k)
                while q and now - q[0] > FAILURE_WINDOW_S:
                    q.popleft()
                if q and len(q) >= MAX_FAILURES:
                    wait = max(wait, int(LOCK_S - (now - q[-1])) + 1)
            return max(0, wait)

    def failure(self, *keys: str) -> None:
        now = self.clock()
        with self._lock:
            for k in keys:
                self._f.setdefault(k, deque(maxlen=MAX_FAILURES * 4)).append(now)

    def success(self, *keys: str) -> None:
        with self._lock:
            for k in keys:
                self._f.pop(k, None)


# ------------------------------------------------------------------------------------------- access rules
# First matching rule wins. None = no session needed. A set = roles allowed (with a session).
PUBLIC_PREFIXES = ("/login", "/_next/", "/favicon", "/icon", "/apple-icon", "/robots.txt")
RULES = [
    ("GET", re.compile(r"^/api/health/?$"), None),
    ("GET", re.compile(r"^/api/auth/me/?$"), None),
    ("POST", re.compile(r"^/api/auth/(login|logout)/?$"), None),
    ("*", re.compile(r"^/api/auth/users"), {"admin"}),
    ("*", re.compile(r"^/api/(diagnostics|data-sources|reports)(/|$)"), {"admin"}),       # internal / technical
    ("GET", re.compile(r"^/api/runs/.+/files/"), {"admin"}),                               # raw result files
    ("POST", re.compile(r"^/api/sim/"), {"admin", "operator"}),                            # starts / stops SUMO
    ("*", re.compile(r"^/api/"), set(ROLES)),
]


def required_roles(method: str, path: str):
    """None = public, a set of roles otherwise. Pages (non-API paths) need a session except the public prefixes."""
    if not path.startswith("/api/"):
        return None if path.startswith(PUBLIC_PREFIXES) else set(ROLES)
    for m, rx, roles in RULES:
        if (m == "*" or m == method) and rx.match(path):
            return roles
    return set(ROLES)


class Auth:
    """Everything the server needs: accounts, sessions, login throttling and the cookie settings."""

    def __init__(self, users: UserStore | None = None, sessions: SessionStore | None = None, guard: LoginGuard | None = None,
                 secure_cookie: bool | None = None):
        self.users = users or UserStore()
        self.sessions = sessions or SessionStore()
        self.guard = guard or LoginGuard()
        env = os.environ.get("ITM_COOKIE_SECURE")
        self.secure_cookie = secure_cookie if secure_cookie is not None else (env == "1" if env else None)

    def user_for(self, token: str | None) -> dict | None:
        s = self.sessions.get(token)
        if s is None:
            return None
        u = self.users.get(s["email"])
        if u is None or u.get("disabled"):
            self.sessions.delete(token)
            return None
        return UserStore.public(u)

    def cookie_kwargs(self, https: bool) -> dict:
        secure = self.secure_cookie if self.secure_cookie is not None else https
        return {"httponly": True, "samesite": "strict", "secure": bool(secure), "path": "/", "max_age": ABSOLUTE_S}


class LoginBody(BaseModel):
    email: str = ""
    password: str = ""


class PasswordBody(BaseModel):
    current: str = ""
    new: str = ""


class NewUser(BaseModel):
    email: str = ""
    name: str = ""
    role: str = "analyst"
    password: str = ""


class SetPassword(BaseModel):
    password: str = ""


class SetStatus(BaseModel):
    disabled: bool = False


def make_router(auth: Auth | None):
    """/api/auth/*. With auth=None (authentication disabled, tests and local development only) /me says so."""
    r = APIRouter(prefix="/api/auth")

    def need(request: Request) -> dict:
        u = getattr(request.state, "user", None)
        if auth is None or u is None:
            raise HTTPException(401, "Session absente ou expirée.")
        return u

    @r.get("/me")
    def me(request: Request):
        if auth is None:
            return {"auth_enabled": False, "authenticated": True, "setup_required": False,
                    "user": {"email": "local", "name": "Accès local (sans authentification)", "role": "admin",
                             "role_label": ROLE_LABELS["admin"]}}
        u = getattr(request.state, "user", None)
        return {"auth_enabled": True, "authenticated": u is not None, "user": u,
                "setup_required": auth.users.count() == 0, "roles": ROLE_LABELS}

    @r.post("/login")
    def login(body: LoginBody, request: Request, response: Response):
        if auth is None:
            raise HTTPException(400, "L'authentification est désactivée sur ce serveur.")
        email = (body.email or "").strip().lower()
        client = f"ip:{request.client.host if request.client else '?'}"
        wait = auth.guard.locked_for(f"mail:{email}", client)
        if wait:
            raise HTTPException(429, f"Trop de tentatives. Réessayez dans {max(1, round(wait / 60))} min.")
        u = auth.users.authenticate(email, body.password)
        if u is None:
            auth.guard.failure(f"mail:{email}", client)
            raise HTTPException(401, "Adresse e-mail ou mot de passe incorrect.")
        auth.guard.success(f"mail:{email}")
        old = request.cookies.get(COOKIE)
        auth.sessions.delete(old)                     # new token at each login (no session fixation)
        token = auth.sessions.create(u["email"])
        response.set_cookie(COOKIE, token, **auth.cookie_kwargs(request.url.scheme == "https"))
        return {"user": u}

    @r.post("/logout")
    def logout(request: Request, response: Response):
        if auth is not None:
            auth.sessions.delete(request.cookies.get(COOKIE))
        response.delete_cookie(COOKIE, path="/")
        return {"ok": True}

    @r.post("/password")
    def change_password(body: PasswordBody, request: Request):
        u = need(request)
        if auth.users.authenticate(u["email"], body.current) is None:
            raise HTTPException(400, "Mot de passe actuel incorrect.")
        try:
            auth.users.set_password(u["email"], body.new)
        except AuthError as e:
            raise HTTPException(400, str(e))
        auth.sessions.delete_user(u["email"], keep=request.cookies.get(COOKIE))   # other sessions closed
        return {"ok": True}

    @r.get("/users")
    def users(request: Request):
        need(request)
        return {"users": auth.users.list(), "roles": ROLE_LABELS}

    @r.post("/users")
    def create_user(body: NewUser, request: Request):
        need(request)
        try:
            return {"user": auth.users.add(body.email, body.name, body.role, body.password)}
        except AuthError as e:
            raise HTTPException(400, str(e))

    @r.post("/users/{email}/password")
    def reset_password(email: str, body: SetPassword, request: Request):
        need(request)
        try:
            u = auth.users.set_password(email, body.password)
        except AuthError as e:
            raise HTTPException(400, str(e))
        auth.sessions.delete_user(u["email"])
        return {"user": u}

    @r.post("/users/{email}/status")
    def set_status(email: str, body: SetStatus, request: Request):
        me_ = need(request)
        if email.strip().lower() == me_["email"] and body.disabled:
            raise HTTPException(400, "Vous ne pouvez pas désactiver votre propre compte.")
        try:
            u = auth.users.set_disabled(email, body.disabled)
        except AuthError as e:
            raise HTTPException(400, str(e))
        if u["disabled"]:
            auth.sessions.delete_user(u["email"])
        return {"user": u}

    return r


def install(app, auth: Auth | None) -> None:
    """Protects every route of `app`: API answers 401/403 in JSON, pages redirect to /login/."""
    from fastapi.responses import JSONResponse, RedirectResponse
    from urllib.parse import quote

    @app.middleware("http")
    async def guard(request, call_next):
        if auth is None:
            return await call_next(request)
        path, method = request.url.path, request.method.upper()
        if method in ("POST", "PUT", "PATCH", "DELETE"):
            origin = request.headers.get("origin")
            if origin and origin.rstrip("/") != f"{request.url.scheme}://{request.headers.get('host', '')}":
                return JSONResponse({"detail": "Requête d'une autre origine refusée."}, status_code=403)
        user = auth.user_for(request.cookies.get(COOKIE))
        request.state.user = user
        roles = required_roles(method, path)
        if roles is None:
            return await call_next(request)
        if user is None:
            if path.startswith("/api/"):
                return JSONResponse({"detail": "Session absente ou expirée."}, status_code=401)
            nxt = quote(path + (f"?{request.url.query}" if request.url.query else ""), safe="/")
            return RedirectResponse(f"/login/?next={nxt}", status_code=303)
        if user["role"] not in roles:
            if path.startswith("/api/"):
                return JSONResponse({"detail": "Votre rôle ne permet pas cette action."}, status_code=403)
        return await call_next(request)

    app.include_router(make_router(auth))


# ------------------------------------------------------------------------------------------- command line
def main(argv=None) -> int:
    import getpass

    p = argparse.ArgumentParser(description="Comptes de l'application Intelligent Traffic Management Luxembourg")
    p.add_argument("--file", help=f"fichier des comptes (défaut {DEFAULT_USERS_FILE})")
    sub = p.add_subparsers(dest="cmd", required=True)
    a = sub.add_parser("add-user")
    a.add_argument("--email", required=True)
    a.add_argument("--name", required=True)
    a.add_argument("--role", choices=ROLES, required=True)
    sp = sub.add_parser("set-password")
    sp.add_argument("--email", required=True)
    sub.add_parser("list")
    for c in ("disable", "enable"):
        sub.add_parser(c).add_argument("--email", required=True)
    args = p.parse_args(argv)
    store = UserStore(args.file)

    def ask() -> str:
        pw = getpass.getpass("Mot de passe : ")
        if pw != getpass.getpass("Confirmez : "):
            raise AuthError("Les deux saisies sont différentes.")
        return pw

    try:
        if args.cmd == "add-user":
            u = store.add(args.email, args.name, args.role, ask())
            print(f"Compte créé : {u['email']} ({u['role_label']}) dans {store.path}")
        elif args.cmd == "set-password":
            u = store.set_password(args.email, ask())
            print(f"Mot de passe changé pour {u['email']}")
        elif args.cmd == "list":
            for u in store.list():
                print(f"{u['email']:40s} {u['role_label']:18s} {'désactivé' if u['disabled'] else 'actif'}")
            if not store.list():
                print(f"Aucun compte dans {store.path}")
        else:
            u = store.set_disabled(args.email, args.cmd == "disable")
            print(f"{u['email']} : {'désactivé' if u['disabled'] else 'activé'}")
    except AuthError as e:
        print(f"Erreur : {e}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
