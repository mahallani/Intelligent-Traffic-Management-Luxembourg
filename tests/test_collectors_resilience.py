"""Resilience of the two collectors for long runs (no network: fetch is injected or collect_once patched).
Run: python -m pytest -p no:cacheprovider tests/test_collectors_resilience.py -q"""
import csv
import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def load(name):
    spec = importlib.util.spec_from_file_location(name, ROOT / f"{name}.py")
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


tr = load("collect_cita_fixed")
ev = load("collect_cita_events_v2")
RAW = ROOT / "data" / "raw"


def test_trailing_newline_repair_isolates_partial_line(tmp_path):
    for mod in (tr, ev):
        f = tmp_path / f"{mod.__name__}.csv"
        f.write_bytes(b"a;b\n1;2\n3;")            # killed in the middle of a line
        assert mod.ensure_trailing_newline(f) is True
        assert f.read_bytes() == b"a;b\n1;2\n3;\n"  # nothing removed, only a newline added
        assert mod.ensure_trailing_newline(f) is False


def test_traffic_light_mode_resume_no_duplicates_no_xml(tmp_path, monkeypatch):
    fetch = lambda road: (RAW / "cita" / f"trafficstatus_{road}.xml").read_bytes()
    out = tmp_path / "cita_traffic_sites_v2.csv"
    seen = set()
    first = tr.collect_once(out, seen, fetch=fetch, raw_dir=None)
    # simulated restart: keys reloaded from the file, same XML again
    seen2 = tr.existing_keys(out)
    second = tr.collect_once(out, seen2, fetch=fetch, raw_dir=None)
    assert first == 247 and second == 0
    with open(out, encoding="utf-8-sig") as fh:
        rows = list(csv.DictReader(fh, delimiter=";"))
    keys = [(r["sensor_id"], r["measurement_timestamp"]) for r in rows]
    assert len(keys) == len(set(keys)) == 247
    assert all(r["sensor_id"] and r["measurement_timestamp"] and r["source_url"] and r["parser_version"] for r in rows)
    assert all(r["collection_timestamp_utc"].endswith("+00:00") for r in rows)
    assert not list(tmp_path.glob("**/*.xml"))      # light mode: no XML archived


def test_events_light_mode_resume(tmp_path):
    fetch = lambda: (RAW / "cita_events" / "situationrecord36.xml").read_bytes()
    rec, sig = tmp_path / "r.csv", tmp_path / "s.csv"
    assert ev.collect_once(rec, sig, set(), fetch=fetch, raw_dir=None) == (18, 18)
    seen = ev.existing_keys(rec, ("record_id", "record_version"))
    assert ev.collect_once(rec, sig, seen, fetch=fetch, raw_dir=None) == (0, 18)
    assert not list(tmp_path.glob("*.xml"))


def test_main_survives_a_failing_cycle(tmp_path, monkeypatch, capsys):
    def boom(*a, **k):
        raise OSError("disk hiccup")
    monkeypatch.setattr(tr, "collect_once", boom)
    assert tr.main(["--once", "--output", str(tmp_path / "t.csv")]) == 0
    monkeypatch.setattr(ev, "collect_once", boom)
    assert ev.main(["--once", "--records", str(tmp_path / "r.csv"), "--sightings", str(tmp_path / "s.csv")]) == 0
    assert capsys.readouterr().out.count("CYCLE ERROR") == 2


def test_main_handles_ctrl_c(tmp_path, monkeypatch, capsys):
    def stop(*a, **k):
        raise KeyboardInterrupt
    monkeypatch.setattr(tr, "collect_once", stop)
    assert tr.main(["--output", str(tmp_path / "t.csv"), "--interval", "1"]) == 0
    assert "stopped by user" in capsys.readouterr().out


def test_max_hours_clean_stop(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(tr, "collect_once", lambda *a, **k: 0)
    assert tr.main(["--output", str(tmp_path / "t.csv"), "--interval", "1", "--max-hours", "0.0000001"]) == 0
    assert "max-hours reached: clean stop" in capsys.readouterr().out
