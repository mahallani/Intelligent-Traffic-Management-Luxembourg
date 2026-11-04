"""Authentication of the control application (app/backend/auth.py, 2026-11-03) - no SUMO, no browser.

Accounts are written to a temporary file; the runs folder is temporary; no simulation is started."""
from __future__ import annotations

import json

import pytest

fastapi = pytest.importorskip("fastapi")
from fastapi.testclient import TestClient  # noqa: E402

from app.backend import auth as A  # noqa: E402
from app.backend.server import create_app  # noqa: E402
from app.backend.sim_manager import SimulationManager  # noqa: E402

PW = "Kirchberg-2026!"


class Clock:
    def __init__(self):
        self.t = 1_000_000.0

    def __call__(self):
        return self.t


@pytest.fixture
def setup(tmp_path):
    store = A.UserStore(tmp_path / "users.json")
    store.add("admin@itm.lu", "Admin", "admin", PW)
    store.add("op@itm.lu", "Opératrice", "operator", PW)
    store.add("ana@itm.lu", "Analyste", "analyst", PW)
    clk = Clock()
    auth = A.Auth(users=store, sessions=A.SessionStore(clock=clk), guard=A.LoginGuard(clock=clk))
    mgr = SimulationManager(runs_dir=tmp_path / "runs")
    with TestClient(create_app(mgr, auth=auth), base_url="http://testserver") as c:
        yield c, store, clk, mgr


def login(c, email, pw=PW):
    return c.post("/api/auth/login", json={"email": email, "password": pw})


def test_password_is_hashed_with_scrypt_never_stored(tmp_path):
    store = A.UserStore(tmp_path / "u.json")
    store.add("x@itm.lu", "X", "analyst", PW)
    raw = (tmp_path / "u.json").read_text(encoding="utf-8")
    assert PW not in raw
    rec = json.loads(raw)["users"][0]["password"]
    assert rec["alg"] == "scrypt" and rec["n"] == 2 ** 14 and len(rec["salt"]) >= 20
    assert A.verify_password(PW, rec) and not A.verify_password(PW + "x", rec)
    store2 = A.UserStore(tmp_path / "v.json")
    store2.add("x@itm.lu", "X", "analyst", PW)
    assert json.loads((tmp_path / "v.json").read_text())["users"][0]["password"]["hash"] != rec["hash"]   # salted


@pytest.mark.parametrize("pw", ["court1", "aaaaaaaaaaaaa", "1234567890123", " espace-au-debut1"])
def test_weak_passwords_are_refused(tmp_path, pw):
    with pytest.raises(A.AuthError):
        A.UserStore(tmp_path / "u.json").add("x@itm.lu", "X", "analyst", pw)


def test_pages_and_api_require_a_session(setup):
    c, *_ = setup
    r = c.get("/api/sim/state")
    assert r.status_code == 401
    r = c.get("/api/xai/decisions")
    assert r.status_code == 401
    r = c.get("/api/runs")
    assert r.status_code == 401
    me = c.get("/api/auth/me").json()
    assert me["auth_enabled"] and not me["authenticated"] and not me["setup_required"]
    assert c.get("/api/health").json()["ok"] is True                       # public, minimal


def test_pages_redirect_to_login_when_frontend_is_built(setup):
    c, *_ = setup
    from app.backend.server import FRONTEND
    if not (FRONTEND / "index.html").exists():
        pytest.skip("frontend not built")
    r = c.get("/xai/", follow_redirects=False)
    assert r.status_code == 303 and r.headers["location"] == "/login/?next=/xai/"
    assert c.get("/login/", follow_redirects=False).status_code == 200


def test_login_sets_an_httponly_strict_cookie_and_logout_ends_the_session(setup):
    c, *_ = setup
    r = login(c, "ADMIN@itm.lu ")
    assert r.status_code == 200 and r.json()["user"]["role"] == "admin"
    cookie = r.headers["set-cookie"]
    assert "itm_session=" in cookie and "HttpOnly" in cookie and "SameSite=strict" in cookie.replace("Strict", "strict")
    assert "password" not in r.text and "hash" not in r.text
    assert c.get("/api/sim/state").status_code == 200
    assert c.get("/api/auth/me").json()["user"]["email"] == "admin@itm.lu"
    c.post("/api/auth/logout")
    assert c.get("/api/sim/state").status_code == 401


def test_wrong_password_unknown_user_and_lockout(setup):
    c, store, clk, _ = setup
    assert login(c, "ana@itm.lu", "mauvais-mot-2026").status_code == 401
    r = login(c, "personne@itm.lu", "mauvais-mot-2026")
    assert r.status_code == 401 and r.json()["detail"] == "Adresse e-mail ou mot de passe incorrect."   # same message
    for _ in range(4):
        login(c, "op@itm.lu", "mauvais-mot-2026")
    r = login(c, "op@itm.lu", PW)                                           # right password, but locked
    assert r.status_code == 429
    clk.t += A.LOCK_S + 1
    c.cookies.clear()
    assert login(c, "op@itm.lu", PW).status_code == 200


def test_session_expires_after_idle_time(setup):
    c, _, clk, _ = setup
    login(c, "ana@itm.lu")
    assert c.get("/api/sim/state").status_code == 200
    clk.t += A.IDLE_S + 1
    assert c.get("/api/sim/state").status_code == 401


def test_roles(setup):
    c, *_ = setup
    login(c, "ana@itm.lu")
    assert c.post("/api/sim/stop").status_code == 403                       # analyst: read only
    assert c.get("/api/diagnostics").status_code == 403                     # technical: admin only
    assert c.get("/api/data-sources").status_code == 403
    assert c.get("/api/reports").status_code == 403
    assert c.get("/api/auth/users").status_code == 403
    assert c.get("/api/xai/decisions").status_code == 200
    assert c.get("/api/incidents/runs").status_code == 200
    c.post("/api/auth/logout")
    login(c, "op@itm.lu")
    assert c.post("/api/sim/stop").status_code == 409                       # allowed, but nothing is running
    assert c.get("/api/data-sources").status_code == 403
    c.post("/api/auth/logout")
    login(c, "admin@itm.lu")
    assert c.get("/api/data-sources").status_code == 200
    assert len(c.get("/api/auth/users").json()["users"]) == 3


def test_cross_origin_post_is_refused(setup):
    c, *_ = setup
    login(c, "admin@itm.lu")
    r = c.post("/api/sim/stop", headers={"Origin": "http://evil.example"})
    assert r.status_code == 403
    r = c.post("/api/sim/stop", headers={"Origin": "http://testserver"})
    assert r.status_code == 409


def test_admin_manages_accounts_and_password_change(setup):
    c, store, *_ = setup
    login(c, "admin@itm.lu")
    r = c.post("/api/auth/users", json={"email": "new@itm.lu", "name": "Nouveau", "role": "analyst", "password": "court"})
    assert r.status_code == 400
    r = c.post("/api/auth/users", json={"email": "new@itm.lu", "name": "Nouveau", "role": "analyst", "password": PW})
    assert r.status_code == 200 and r.json()["user"]["role"] == "analyst"
    assert c.post("/api/auth/users/admin@itm.lu/status", json={"disabled": True}).status_code == 400   # not yourself
    assert c.post("/api/auth/users/new@itm.lu/status", json={"disabled": True}).json()["user"]["disabled"]
    c.post("/api/auth/logout")
    assert login(c, "new@itm.lu").status_code == 401                        # disabled account
    login(c, "ana@itm.lu")
    assert c.post("/api/auth/password", json={"current": "faux-faux-2026", "new": "Nouveau-mdp-2026"}).status_code == 400
    assert c.post("/api/auth/password", json={"current": PW, "new": "Nouveau-mdp-2026"}).status_code == 200
    c.post("/api/auth/logout")
    assert login(c, "ana@itm.lu").status_code == 401
    assert login(c, "ana@itm.lu", "Nouveau-mdp-2026").status_code == 200


def test_disabled_auth_reports_local_admin(tmp_path):
    with TestClient(create_app(SimulationManager(runs_dir=tmp_path / "r"))) as c:
        me = c.get("/api/auth/me").json()
        assert me["auth_enabled"] is False and me["user"]["role"] == "admin"
        assert c.get("/api/sim/state").status_code == 200


def test_setup_required_without_accounts(tmp_path):
    auth = A.Auth(users=A.UserStore(tmp_path / "none.json"))
    with TestClient(create_app(SimulationManager(runs_dir=tmp_path / "r"), auth=auth)) as c:
        assert c.get("/api/auth/me").json()["setup_required"] is True


def test_cli_creates_an_account(tmp_path, monkeypatch):
    answers = iter([PW, PW])
    monkeypatch.setattr("getpass.getpass", lambda prompt="": next(answers))
    f = tmp_path / "users.json"
    assert A.main(["--file", str(f), "add-user", "--email", "cli@itm.lu", "--name", "CLI", "--role", "operator"]) == 0
    assert A.UserStore(f).authenticate("cli@itm.lu", PW)["role"] == "operator"
