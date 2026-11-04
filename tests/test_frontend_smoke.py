"""Smoke tests of the web interface (Next.js static export served by the Python backend) - without SUMO.
2026-11-03: rewritten for the redesigned interface with authentication (previous version: test_frontend_smoke.py.bak_20261103).

Checked with a headless Chromium driven by Playwright for Python, with authentication ON (temporary accounts file):
  T0 login        : a page without session redirects to /login/; wrong password refused; right password opens the page asked
  T1 navigation   : the sidebar links open the right page and only that link is marked active (admin and analyst menus)
  T2 XAI page     : waiting state without simulation and no pre-computed figure; a decision of a recorded S3 run explained
                    with the values of agents/xai/shap_qtable.py (chart, Q values, technical view); a fallback decision
                    refused with its reason and no SHAP value; filters (SHAP status, junction, search) and the latest
                    decision selected by default (2026-11-04); clear message when the server does not answer
  T3 errors       : no console error, no JavaScript exception, no failed request, no HTTP status >= 400 on each page
  T4 layout       : no horizontal scrolling at 1440x900, 768x1024 and 390x844 (screenshots kept in the pytest temp dir)
  T5 identity     : application name and browser-tab titles
  T6 roles        : an analyst sees no technical section, cannot start a simulation, and no page shows internal paths
  T7 safety       : no simulation was started, the runs folder is unchanged

SUMO safety
  The backend runs in this process (create_app) with a SimulationManager whose runs folder is a temporary directory.
  SUMO can only be started by POST /api/sim/start; the tests never press a simulation button and the four
  simulation-control routes POST /api/sim/{start,pause,resume,stop} are intercepted: such a request is aborted and makes
  the test fail. The recorded S3 run used by T2 is COPIED into the temporary runs folder (the original is only read).

Nothing in the project is written. Skipped, with the reason, when Playwright or its Chromium is not installed, or when
app/frontend/out is missing or was built before the redesign (then rebuild the frontend first).

    python -m pytest tests/test_frontend_smoke.py -v -ra
"""
from __future__ import annotations

import hashlib
import re
import shutil
import socket
import threading
import time
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "app" / "frontend" / "out"
S3_RUN = "20261022_141518_S3_rl_qlearning_x1_seed1_ambulance_prio"
S3_SRC = ROOT / "sumo" / "lust_4_intersections" / "output" / "app_runs" / S3_RUN / "decisions.csv"
EVAL_DIR = ROOT / "sumo" / "lust_4_intersections" / "output" / "experiments_v2b" / "runs"

APP_NAME = "Intelligent Traffic Management Luxembourg"
PW = "Smoke-Test-2026!"
USERS = {"admin": "admin@test.lu", "operator": "operateur@test.lu", "analyst": "analyste@test.lu"}
PAGES = [  # (path, sidebar label, h1 text, browser-tab title, admin only)
    ("/", "Vue d'ensemble", "Vue d'ensemble", APP_NAME, False),
    ("/supervision/", "Supervision du trafic", "Supervision du trafic", APP_NAME, False),
    ("/simulation/", "Simulation", "Simulation", APP_NAME, False),
    ("/carrefours/", "Carrefours", "Carrefours", APP_NAME, False),
    ("/previsions/", "Prévisions IA", "Prévisions IA", APP_NAME, False),
    ("/incidents/", "Incidents et alertes", "Incidents et alertes", APP_NAME, False),
    ("/xai/", "IA explicable", "Explicabilité de l'IA (XAI)", "ITM Luxembourg – Explicabilité de l'IA", False),
    ("/rapports/", "Rapports", "Rapports", APP_NAME, False),
    ("/parametres/", "Paramètres", "Paramètres", APP_NAME, False),
    ("/technique/", "Section technique", "Section technique", APP_NAME, True),
]
VIEWPORTS = {"desktop": (1440, 900), "tablet": (768, 1024), "mobile": (390, 844)}
SIM_CONTROL = re.compile(r"/api/sim/(start|pause|resume|stop)/?$")
SETTLE_MS = 2500
INTERNAL = ["sumo/lust", "app_runs", "decisions.csv", "python -m", "qtable", ".json", "S3_rl_qlearning"]

sync_api = pytest.importorskip("playwright.sync_api", reason="Playwright for Python is not installed")
if not (OUT / "index.html").exists():
    pytest.skip("app/frontend/out is missing: build the frontend first (npm run build in app/frontend)", allow_module_level=True)
if not (OUT / "login" / "index.html").exists():
    pytest.skip("app/frontend/out was built before the redesign (no /login/ page): rebuild the frontend (npm run build)",
                allow_module_level=True)


def _free_port() -> int:
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


@pytest.fixture(scope="module")
def backend(tmp_path_factory):
    """The real backend (API + static frontend) with authentication, never asked to start a simulation."""
    uvicorn = pytest.importorskip("uvicorn")
    from app.backend.auth import Auth, UserStore
    from app.backend.server import create_app
    from app.backend.sim_manager import SimulationManager

    runs = tmp_path_factory.mktemp("app_runs_copy")
    copied = False
    if S3_SRC.exists():
        (runs / S3_RUN).mkdir()
        shutil.copy(S3_SRC, runs / S3_RUN / "decisions.csv")
        copied = True
    store = UserStore(tmp_path_factory.mktemp("accounts") / "users.json")
    for role, mail in USERS.items():
        store.add(mail, f"Test {role}", role, PW)
    manager = SimulationManager(runs_dir=runs)
    app = create_app(manager, auth=Auth(users=store))
    port = _free_port()
    server = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=port, log_level="warning"))
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    t0 = time.time()
    while not server.started:
        if time.time() - t0 > 30 or not thread.is_alive():
            pytest.fail("the backend did not start")
        time.sleep(0.05)
    yield {"base": f"http://127.0.0.1:{port}", "manager": manager, "s3_copied": copied}
    server.should_exit = True
    thread.join(timeout=15)


@pytest.fixture(scope="module")
def browser():
    pw = sync_api.sync_playwright().start()
    try:
        br = pw.chromium.launch()
    except Exception as exc:  # noqa: BLE001
        pw.stop()
        pytest.skip(f"Chromium for Playwright is not available ({str(exc).splitlines()[0]})")
    yield br
    br.close()
    pw.stop()


@pytest.fixture(scope="module")
def shots(tmp_path_factory):
    d = tmp_path_factory.mktemp("ui_screenshots")
    print(f"\nscreenshots: {d}")
    return d


class Watched:
    """A browser context (own cookies) recording console errors, JS exceptions, failed requests and blocked sim calls."""

    def __init__(self, browser, viewport):
        self.ctx = browser.new_context(viewport={"width": viewport[0], "height": viewport[1]})
        self.page = self.ctx.new_page()
        self.errors, self.sim_calls, self.allowed = [], [], []
        self.page.on("console", lambda m: m.type == "error" and not any(a in (m.location or {}).get("url", "") for a in self.allowed)
                     and self.errors.append(f"console: {m.text} ({(m.location or {}).get('url', '')})"))
        self.page.on("pageerror", lambda e: self.errors.append(f"exception: {e}"))
        self.page.on("response", lambda r: r.status >= 400 and not any(a in r.url for a in self.allowed)
                     and self.errors.append(f"HTTP {r.status} {r.url}"))
        self.page.on("requestfailed", lambda r: SIM_CONTROL.search(r.url) is None
                     and self.errors.append(f"request failed: {r.url} ({r.failure})"))
        self.page.route(SIM_CONTROL, self._guard)
        if not any(EVAL_DIR.glob("*_x5_seed*")):           # this copy of the project has no evaluation series
            self.allowed.append("/api/compare")

    def _guard(self, route):
        if route.request.method == "POST":
            self.sim_calls.append(route.request.url)
            route.abort()
        else:
            route.continue_()

    def login(self, base, role="admin", path="/"):
        self.page.goto(f"{base}/login/?next={path}", wait_until="load")
        self.page.fill("#email", USERS[role])
        self.page.fill("#password", PW)
        self.page.click("button[type=submit]")
        self.page.wait_for_url(base + path)
        self.page.wait_for_timeout(800)
        return self.page

    def open(self, base, path):
        self.page.goto(base + path, wait_until="load")
        self.page.wait_for_timeout(SETTLE_MS)
        return self.page

    def close(self):
        self.ctx.close()


@pytest.fixture
def watched(browser):
    made = []

    def make(viewport=VIEWPORTS["desktop"]):
        w = Watched(browser, viewport)
        made.append(w)
        return w
    yield make
    for w in made:
        w.close()


# ---------------------------------------------------------------------------------------------------- tests
def test_login_required_then_redirects_to_the_page_asked(backend, watched):
    w = watched()
    p = w.page
    p.goto(backend["base"] + "/incidents/", wait_until="load")
    p.wait_for_url(re.compile(r"/login/\?next=/incidents/"))
    assert p.locator("h1").inner_text() == APP_NAME
    p.click("button[type=submit]")                                    # empty form: client-side validation, no request
    assert p.get_by_text("Saisissez votre adresse e-mail.").count() == 1
    p.fill("#email", USERS["admin"])
    p.fill("#password", "mauvais-mot-de-passe-1")
    p.click("button[type=submit]")
    p.get_by_text("Adresse e-mail ou mot de passe incorrect.").wait_for()
    assert p.locator("#password").get_attribute("type") == "password"
    p.get_by_role("button", name="Afficher le mot de passe").click()
    assert p.locator("#password").get_attribute("type") == "text"
    p.fill("#password", PW)
    p.click("button[type=submit]")
    p.wait_for_url(backend["base"] + "/incidents/")
    p.locator("h1", has_text="Incidents et alertes").wait_for()
    cookies = {c["name"]: c for c in w.ctx.cookies()}
    assert cookies["itm_session"]["httpOnly"] and cookies["itm_session"]["sameSite"] == "Strict"
    assert p.evaluate("() => document.cookie").find("itm_session") == -1         # not readable by scripts
    assert p.evaluate("() => JSON.stringify(Object.keys(localStorage))").find("session") == -1
    w.errors = [e for e in w.errors if "401" not in e]                            # the refused login answers 401
    assert w.errors == [] and w.sim_calls == []


@pytest.mark.parametrize("role", ["admin", "analyst"])
def test_sidebar_opens_every_page(backend, watched, role):
    w = watched()
    page = w.login(backend["base"], role)
    expected = [p for p in PAGES if role == "admin" or not p[4]]
    links = page.locator("aside.sidebar nav a")
    assert [t.strip() for t in links.all_inner_texts()] == [p[1] for p in expected]
    for path, label, h1, _, _ in expected:
        page.locator("aside.sidebar nav a", has_text=label).first.click()
        page.wait_for_url(backend["base"] + path)
        page.locator("h1", has_text=h1).first.wait_for(state="visible")
        active = page.locator('aside.sidebar nav a[aria-current="page"]')
        assert [t.strip() for t in active.all_inner_texts()] == [label], f"active link on {path}"
    assert w.errors == [] and w.sim_calls == []


def _fr6(v: float) -> str:
    txt = f"{abs(v):.6f}".replace(".", ",")
    return ("+" if v > 0 else "−" if v < 0 else "") + txt


def test_xai_page_waits_without_simulation_and_shows_no_precomputed_figure(backend, watched):
    w = watched()
    w.login(backend["base"], "analyst")
    page = w.open(backend["base"], "/xai/")
    assert "Aucune simulation" in page.locator("main").inner_text()
    assert page.get_by_text("En attente d'une simulation").count() == 1
    assert page.locator("main img").count() == 0 and page.locator('[aria-label^="Contributions SHAP"]').count() == 0
    assert w.errors == [] and w.sim_calls == []


def test_xai_page_explains_a_recorded_s3_decision_with_the_engine_values(backend, watched):
    if not backend["s3_copied"]:
        pytest.skip(f"recorded S3 run not present ({S3_RUN})")
    from agents.xai import shap_qtable as sx
    ref = sx.explain_logged_decision()
    w = watched()
    w.login(backend["base"], "analyst")
    page = w.open(backend["base"], "/xai/")
    page.select_option("#xai-run", S3_RUN)
    items = page.locator("main button[aria-pressed]")
    items.first.wait_for(state="visible")
    assert items.count() == 613
    items.filter(has_text="07:29:01").filter(has_text="Carrefour 4").first.click()
    chart = page.locator('[role=img][aria-label^="Contributions SHAP"]')
    chart.wait_for(state="visible", timeout=15000)
    label = chart.get_attribute("aria-label")
    for c in ref["contributions"]:
        assert f"{c['variable']} {_fr6(c['shap'])}" in label, (c["variable"], label)
    main = page.locator("main").inner_text()
    assert "Explication simplifiée" in main and "ne mesurent pas l'effet" in main
    assert "-1,481" in main.replace("\u2212", "-") and "-4,651" in main.replace("\u2212", "-")   # Q values of the table
    page.get_by_role("tab", name="Vue technique").click()                 # exact values of the engine
    tech = page.locator("main").inner_text().replace("\u2212", "-")
    for c in ref["contributions"]:
        assert f"{c['shap']:+.6f}".replace(".", ",").replace("+0,000000", "0,000000") in tech.replace("+0,000000", "0,000000") or \
            abs(c["shap"]) < 1e-12, c["variable"]
    page.get_by_role("tab", name="Vue simplifiée").click()
    items.filter(has_text="règle de secours").first.click()
    assert page.get_by_text("Pas d'explication SHAP pour cette décision").count() == 1
    assert page.locator('[aria-label^="Contributions SHAP"]').count() == 0      # no SHAP values for it
    assert w.errors == [] and w.sim_calls == []


def test_xai_filters_and_latest_decision(backend, watched):
    if not backend["s3_copied"]:
        pytest.skip(f"recorded S3 run not present ({S3_RUN})")
    w = watched()
    w.login(backend["base"], "analyst")
    page = w.open(backend["base"], "/xai/")
    page.select_option("#xai-run", S3_RUN)
    items = page.locator("main button[aria-pressed]")
    items.first.wait_for(state="visible")
    assert items.first.get_attribute("aria-pressed") == "true"            # the most recent decision is selected
    page.locator("h2", has_text="Décision du").first.wait_for()
    page.get_by_role("radio", name="SHAP", exact=True).click()
    n_shap = items.count()
    assert n_shap == 259 and items.filter(has_text="non admissible").count() == 0
    page.get_by_role("radio", name="Non adm.").click()
    assert items.count() == 613 - 259
    page.get_by_role("radio", name="Tous").click()
    page.select_option("#xai-tls", "Carrefour 4")
    assert items.count() == items.filter(has_text="Carrefour 4").count() > 0
    page.select_option("#xai-tls", "")
    page.fill("#xai-q", "07:29:01")
    assert 1 <= items.count() <= 4
    assert w.errors == [] and w.sim_calls == []


def test_xai_page_reports_an_unreachable_server(backend, watched):
    w = watched()
    w.login(backend["base"], "admin")
    w.page.route("**/api/xai/**", lambda route: route.abort())
    w.page.route("**/api/health", lambda route: route.abort())
    w.page.goto(backend["base"] + "/xai/", wait_until="load")
    alert = w.page.get_by_role("alert").filter(has_text="Serveur injoignable")
    alert.wait_for(state="visible", timeout=10000)
    assert "python -m app.backend.server" in alert.inner_text()           # the administrator gets the command
    assert w.sim_calls == []


@pytest.mark.parametrize("path", [p[0] for p in PAGES])
def test_no_console_or_network_error(backend, watched, path):
    w = watched()
    w.login(backend["base"], "admin")
    w.open(backend["base"], path)
    assert w.errors == [], "\n".join(w.errors)
    assert w.sim_calls == []


@pytest.mark.parametrize("vp", list(VIEWPORTS))
@pytest.mark.parametrize("path", ["/login/"] + [p[0] for p in PAGES])
def test_no_horizontal_scroll(backend, watched, shots, path, vp):
    w = watched(VIEWPORTS[vp])
    if path != "/login/":
        w.login(backend["base"], "admin")
    page = w.open(backend["base"], path)
    sizes = page.evaluate("() => [document.documentElement.scrollWidth, window.innerWidth]")
    name = (path.strip("/") or "accueil") + f"_{vp}.png"
    page.screenshot(path=str(shots / name), full_page=True)
    assert sizes[0] <= sizes[1], f"{path} at {vp}: page is {sizes[0]} px wide for a {sizes[1]} px window (see {name})"
    assert w.errors == [] and w.sim_calls == []


def test_application_name_and_titles(backend, watched):
    w = watched()
    w.login(backend["base"], "admin")
    for path, _, _, title, _ in PAGES:
        page = w.open(backend["base"], path)
        assert page.title() == title, f"{path}: tab title {page.title()!r}"
        assert page.locator("header.topbar .tb-platform").inner_text() == APP_NAME
    assert w.errors == [] and w.sim_calls == []


def test_analyst_role_limits_and_no_internal_information(backend, watched):
    w = watched()
    w.login(backend["base"], "analyst")
    page = w.open(backend["base"], "/technique/")
    assert page.get_by_text("Accès réservé aux administrateurs.").count() == 1
    page = w.open(backend["base"], "/simulation/")
    assert page.get_by_role("button", name="Démarrer").is_disabled()
    assert page.get_by_text("Consultation seule.").count() == 1
    for path, *_ in PAGES[:-1]:
        text = w.open(backend["base"], path).locator("main").inner_text()
        for word in INTERNAL:
            assert word not in text, f"internal information {word!r} shown to an analyst on {path}"
    assert w.sim_calls == []


def test_logout_ends_the_session(backend, watched):
    w = watched()
    page = w.login(backend["base"], "operator")
    page.locator(".user-btn").click()
    page.get_by_role("menuitem", name="Se déconnecter").click()
    page.wait_for_url(re.compile(r"/login/"))
    page.goto(backend["base"] + "/supervision/", wait_until="load")
    page.wait_for_url(re.compile(r"/login/\?next=/supervision/"))
    assert w.sim_calls == []


def test_no_simulation_was_started(backend):
    assert backend["manager"].state().get("status") == "idle"
    expected = [S3_RUN] if backend["s3_copied"] else []
    assert sorted(p.name for p in backend["manager"].runs_dir.iterdir()) == expected
    if backend["s3_copied"]:
        assert hashlib.sha256((backend["manager"].runs_dir / S3_RUN / "decisions.csv").read_bytes()).digest() == \
            hashlib.sha256(S3_SRC.read_bytes()).digest()
