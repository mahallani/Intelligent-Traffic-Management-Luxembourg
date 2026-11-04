"""Tests of collect_cita_events_v2.py on data/raw/cita_events/situationrecord36.xml (no network).
Run:  python -m pytest tests/test_collect_cita_events_v2.py -v"""
import csv
import importlib.util
import tempfile
import unittest
import xml.etree.ElementTree as ET
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
XML = ROOT / "data" / "raw" / "cita_events" / "situationrecord36.xml"
spec = importlib.util.spec_from_file_location("ev", ROOT / "collect_cita_events_v2.py")
ev = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ev)
NS = {"sit": "http://datex2.eu/schema/3/situation", "com": "http://datex2.eu/schema/3/common",
      "loc": "http://datex2.eu/schema/3/locationReferencing"}
XSI = "{http://www.w3.org/2001/XMLSchema-instance}type"


def oracle():
    root = ET.parse(XML).getroot()
    out = {}
    for sit in root.findall(".//sit:situation", NS):
        for rec in sit.findall("sit:situationRecord", NS):
            out[(rec.get("id"), rec.get("version"))] = {
                "situation": sit.get("id"), "type": rec.get(XSI).split(":")[-1],
                "creation": rec.findtext("sit:situationRecordCreationTime", namespaces=NS),
                "version_time": rec.findtext("sit:situationRecordVersionTime", namespaces=NS),
                "start": rec.findtext("sit:validity/com:validityTimeSpecification/com:overallStartTime", namespaces=NS),
                "road": rec.findtext(".//loc:roadInformation/loc:roadName", namespaces=NS),
                "lat": rec.findtext(".//loc:pointByCoordinates/loc:pointCoordinates/loc:latitude", namespaces=NS),
                "lanes_restricted": rec.findtext("sit:impact/sit:numberOfLanesRestricted", namespaces=NS),
                "safety": rec.findtext("sit:safetyRelatedMessage", namespaces=NS)}
    return out


class TestEventsParser(unittest.TestCase):
    def setUp(self):
        self.rows = ev.parse_events_xml(XML.read_bytes(), "2026-10-10T20:00:00+00:00")
        self.truth = oracle()

    def test_all_records_with_real_ids(self):
        self.assertEqual(len(self.rows), 18)
        self.assertEqual({(r["record_id"], r["record_version"]) for r in self.rows}, set(self.truth))
        self.assertEqual(len({r["situation_id"] for r in self.rows}), 12)

    def test_values_match_independent_reading(self):
        for r in self.rows:
            t = self.truth[(r["record_id"], r["record_version"])]
            with self.subTest(record=r["record_id"]):
                self.assertEqual(r["situation_id"], t["situation"])
                self.assertEqual(r["record_type"], t["type"])
                self.assertEqual(r["creation_time"], t["creation"])
                self.assertEqual(r["version_time"], t["version_time"])
                self.assertEqual(r["overall_start_time"], t["start"])
                self.assertEqual(r["road_name"], t["road"])
                self.assertEqual(r["latitude"], t["lat"])
                self.assertEqual(r["lanes_restricted"], t["lanes_restricted"])
                self.assertEqual(r["safety_related_message"], t["safety"])

    def test_record_id_prefixed_by_situation_id(self):
        for r in self.rows:
            self.assertTrue(r["record_id"].startswith(r["situation_id"] + "-"))

    def test_type_comes_from_xsi_type_not_comment(self):
        self.assertTrue(all(r["record_type"] for r in self.rows))
        self.assertIn("MaintenanceWorks", {r["record_type"] for r in self.rows})


class TestEventsWriting(unittest.TestCase):
    def test_idempotent_and_sightings(self):
        fetch = lambda: XML.read_bytes()
        with tempfile.TemporaryDirectory() as d:
            rec, sig = Path(d) / "r.csv", Path(d) / "s.csv"
            seen = set()
            self.assertEqual(ev.collect_once(rec, sig, seen, fetch=fetch), (18, 18))
            self.assertEqual(ev.collect_once(rec, sig, seen, fetch=fetch), (0, 18))
            seen2 = ev.existing_keys(rec, ("record_id", "record_version"))
            self.assertEqual(ev.collect_once(rec, sig, seen2, fetch=fetch), (0, 18))
            with open(rec, encoding="utf-8-sig") as fh:
                rows = list(csv.DictReader(fh, delimiter=";"))
            with open(sig, encoding="utf-8-sig") as fh:
                sight = list(csv.DictReader(fh, delimiter=";"))
        self.assertEqual(len(rows), 18)
        self.assertEqual(len(sight), 54)

    def test_refuses_legacy_and_raw(self):
        for f in ev.LEGACY_FILES:
            with self.subTest(f=f.name), self.assertRaises(SystemExit):
                ev.main(["--once", "--records", str(f)])
        with self.assertRaises(SystemExit):
            ev.check_output(ROOT / "data" / "raw" / "x.csv", ev.RECORD_COLUMNS)

    def test_malformed_xml_raises_without_writing(self):
        with tempfile.TemporaryDirectory() as d:
            rec = Path(d) / "r.csv"
            with self.assertRaises(ET.ParseError):
                ev.collect_once(rec, Path(d) / "s.csv", set(), fetch=lambda: b"<broken")
            self.assertFalse(rec.exists())


if __name__ == "__main__":
    unittest.main()
