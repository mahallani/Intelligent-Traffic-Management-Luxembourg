"""
Tests of the CITA traffic collector (parser v2.1) on the raw XML snapshots of data/raw/cita/
(no network; files are only written in temporary folders outside the project).

Run from the project root:
    python -m pytest tests/test_collect_cita_fixed.py -v      (or: python -m unittest tests.test_collect_cita_fixed -v)
"""
import csv
import importlib.util
import tempfile
import unittest
import xml.etree.ElementTree as ET
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "data" / "raw" / "cita"
NS = {"d": "http://datex2.eu/schema/2/2_0"}
XSI = "{http://www.w3.org/2001/XMLSchema-instance}type"
ROADS = ["a1", "a3", "a4", "a6", "a7", "a13", "b40"]
EXPECTED_SENSORS = {"a1": 40, "a3": 29, "a4": 25, "a6": 36, "a7": 48, "a13": 51, "b40": 18}

spec = importlib.util.spec_from_file_location("collector", ROOT / "collect_cita_fixed.py")
collector = importlib.util.module_from_spec(spec)
spec.loader.exec_module(collector)          # safe: the loop only runs under __main__

RECOMMENDED = ["measurement_timestamp", "collection_timestamp_utc", "sensor_id", "road", "direction",
               "latitude", "longitude", "speed_kmh", "occupancy_percent", "vehicle_flow_rate", "source_url"]


def oracle(road):
    """Independent reading with explicit namespaced XPath: {sensor_id: values}."""
    root = ET.parse(RAW / f"trafficstatus_{road}.xml").getroot()
    out = {}
    for sm in root.findall(".//d:payloadPublication/d:siteMeasurements", NS):
        sid = sm.find("d:measurementSiteReference", NS).get("id")
        v = {"ts": sm.findtext("d:measurementTimeDefault", namespaces=NS), "speed": None, "occ": None,
             "flow": None, "period": None, "lat": None, "lon": None, "dir": None, "road": None}
        for b in sm.findall("d:measuredValue/d:measuredValue/d:basicData", NS):
            t = b.get(XSI)
            if t == "TrafficSpeed":
                v["speed"] = b.findtext("d:averageVehicleSpeed/d:speed", namespaces=NS)
                v["lat"] = b.findtext("d:pertinentLocation/d:locationForDisplay/d:latitude", namespaces=NS)
                v["lon"] = b.findtext("d:pertinentLocation/d:locationForDisplay/d:longitude", namespaces=NS)
                v["dir"] = b.findtext("d:pertinentLocation/d:linearWithinLinearElement/d:directionBoundOnLinearSection", namespaces=NS)
                v["road"] = b.findtext("d:pertinentLocation/d:linearWithinLinearElement/d:linearElement/d:roadNumber", namespaces=NS)
            elif t == "TrafficConcentration":
                v["occ"] = b.findtext("d:occupancy/d:percentage", namespaces=NS)
            elif t == "TrafficFlow":
                v["flow"] = b.findtext("d:vehicleFlow/d:vehicleFlowRate", namespaces=NS)
                v["period"] = b.findtext("d:measurementOrCalculationPeriod", namespaces=NS)
        out[sid] = v
    return out


def parse(road):
    return collector.parse_traffic_xml((RAW / f"trafficstatus_{road}.xml").read_bytes(), road,
                                       "2026-10-10T20:00:00+00:00", "2026-10-10T21:00:00+01:00")


def fetch_raw(road):
    return (RAW / f"trafficstatus_{road}.xml").read_bytes()


def read_out(path):
    with open(path, encoding="utf-8-sig", newline="") as fh:
        return list(csv.DictReader(fh, delimiter=";"))


SYNTHETIC = b"""<?xml version="1.0"?>
<d2LogicalModel xmlns="http://datex2.eu/schema/2/2_0" xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">
 <payloadPublication xsi:type="MeasuredDataPublication"><publicationTime>2026-10-10T10:00:00+02:00</publicationTime>
  <siteMeasurements><measurementSiteReference id="X.1" version="1"/><measurementTimeDefault>2026-10-10T09:55:00+02:00</measurementTimeDefault></siteMeasurements>
  <siteMeasurements><measurementSiteReference id="X.2" version="1"/><measurementTimeDefault>2026-10-10T09:55:00+02:00</measurementTimeDefault>
   <measuredValue index="3"><measuredValue><basicData xsi:type="TrafficFlow"><vehicleFlow><vehicleFlowRate>120</vehicleFlowRate></vehicleFlow></basicData></measuredValue></measuredValue></siteMeasurements>
  <siteMeasurements><measurementSiteReference id="X.2" version="1"/><measurementTimeDefault>2026-10-10T09:55:00+02:00</measurementTimeDefault>
   <measuredValue index="3"><measuredValue><basicData xsi:type="TrafficFlow"><vehicleFlow><vehicleFlowRate>120</vehicleFlowRate></vehicleFlow></basicData></measuredValue></measuredValue></siteMeasurements>
  <siteMeasurements><measurementTimeDefault>2026-10-10T09:55:00+02:00</measurementTimeDefault></siteMeasurements>
 </payloadPublication></d2LogicalModel>"""


class TestHierarchyAndValues(unittest.TestCase):
    def test_raw_files_present(self):
        for road in ROADS:
            self.assertTrue((RAW / f"trafficstatus_{road}.xml").exists(), road)

    def test_schema_has_recommended_columns(self):
        for c in RECOMMENDED:
            self.assertIn(c, collector.COLUMNS)
        self.assertNotIn("vehicle_flow", collector.COLUMNS, "no invented vehicle_flow column (absent from feed)")

    def test_one_row_per_sensor_all_sensors_kept(self):
        for road in ROADS:
            rows = parse(road)
            ids = [r["sensor_id"] for r in rows]
            with self.subTest(road=road):
                self.assertEqual(len(rows), EXPECTED_SENSORS[road])
                self.assertEqual(len(set(ids)), len(ids))
                self.assertEqual(set(ids), set(oracle(road)))

    def test_each_value_belongs_to_its_own_sensor(self):
        for road in ROADS:
            truth = oracle(road)
            for r in parse(road):
                t = truth[r["sensor_id"]]
                with self.subTest(road=road, sensor=r["sensor_id"]):
                    self.assertEqual(r["measurement_timestamp"], t["ts"])
                    self.assertEqual(r["speed_kmh"], t["speed"])
                    self.assertEqual(r["occupancy_percent"], t["occ"])
                    self.assertEqual(r["vehicle_flow_rate"], t["flow"])
                    self.assertEqual(r["flow_period_s"], t["period"])
                    self.assertEqual((r["latitude"], r["longitude"]), (t["lat"], t["lon"]))
                    self.assertEqual(r["direction"], t["dir"])
                    self.assertEqual(r["road_number"], t["road"])

    def test_sensor_road_prefix_matches_feed_road(self):
        for road in ROADS:
            for r in parse(road):
                self.assertTrue(r["sensor_id"].upper().startswith(road.upper() + "."), r["sensor_id"])

    def test_no_merging_values_vary_across_sensors(self):
        for road in ("a1", "a4", "a13"):
            rows = parse(road)
            self.assertGreater(len({r["speed_kmh"] for r in rows}), 5)
            self.assertGreater(len({(r["latitude"], r["longitude"]) for r in rows if r["latitude"]}), 5)

    def test_units_and_plausible_ranges(self):
        for road in ROADS:
            for r in parse(road):
                if r["speed_kmh"] is not None:
                    self.assertTrue(0 <= float(r["speed_kmh"]) <= 250)
                if r["occupancy_percent"] is not None:
                    self.assertTrue(0 <= float(r["occupancy_percent"]) <= 100)
                if r["vehicle_flow_rate"] is not None:
                    self.assertTrue(0 <= float(r["vehicle_flow_rate"]) <= 10000)
                if r["flow_period_s"] is not None:
                    self.assertEqual(float(r["flow_period_s"]), 3600.0)

    def test_measurement_time_explicit_offset_and_distinct_from_collection_time(self):
        for road in ROADS:
            for r in parse(road):
                ts = datetime.fromisoformat(r["measurement_timestamp"])
                self.assertIsNotNone(ts.utcoffset(), "measurement time must keep its explicit offset")
                self.assertNotEqual(r["measurement_timestamp"], r["collection_timestamp_utc"])

    def test_missing_measurements_stay_none(self):
        partial = [r for road in ROADS for r in parse(road) if r["measured_values"] < 3]
        self.assertGreater(len(partial), 0)
        for r in partial:
            if r["measured_values"] == 1:
                self.assertIsNone(r["speed_kmh"])
                self.assertIsNone(r["latitude"])
                self.assertIsNotNone(r["vehicle_flow_rate"])


class TestWritingAndProtection(unittest.TestCase):
    def test_idempotent_same_xml_and_restart(self):
        with tempfile.TemporaryDirectory() as d:
            out = Path(d) / "sites.csv"
            seen = collector.existing_keys(out)
            n1 = collector.collect_once(out, seen, fetch=fetch_raw)
            n2 = collector.collect_once(out, seen, fetch=fetch_raw)
            n3 = collector.collect_once(out, collector.existing_keys(out), fetch=fetch_raw)
            rows = read_out(out)
        self.assertEqual((n1, n2, n3), (247, 0, 0))
        self.assertEqual(len(rows), 247)
        self.assertEqual(len({(r["sensor_id"], r["measurement_timestamp"]) for r in rows}), 247)
        self.assertEqual(list(rows[0].keys()), collector.COLUMNS)
        self.assertTrue(all(r["collection_timestamp_utc"].endswith("+00:00") for r in rows))

    def test_duplicates_inside_one_response_and_unattributable_rows(self):
        rows = collector.parse_traffic_xml(SYNTHETIC, "x", "t", "t")
        self.assertEqual(len(rows), 4)                               # parser keeps everything...
        with tempfile.TemporaryDirectory() as d:
            n = collector.append_rows(rows, Path(d) / "o.csv", set())
            written = read_out(Path(d) / "o.csv")
        self.assertEqual(n, 2)                                       # ...writer: X.1, X.2 once, no id-less row
        self.assertEqual(sorted(r["sensor_id"] for r in written), ["X.1", "X.2"])
        x1 = next(r for r in written if r["sensor_id"] == "X.1")
        self.assertEqual((x1["speed_kmh"], x1["vehicle_flow_rate"]), ("", ""))   # nothing invented

    def test_malformed_xml_for_one_road_does_not_stop_the_others(self):
        def fetch(road):
            return b"<broken" if road == "a3" else fetch_raw(road)
        with tempfile.TemporaryDirectory() as d:
            n = collector.collect_once(Path(d) / "o.csv", set(), fetch=fetch)
        self.assertEqual(n, 247 - 29)

    def test_raw_xml_archived(self):
        with tempfile.TemporaryDirectory() as d:
            collector.collect_once(Path(d) / "o.csv", set(), fetch=fetch_raw, raw_dir=Path(d) / "raw")
            files = sorted(p.name for p in (Path(d) / "raw").iterdir())
            self.assertEqual(len(files), 7)
            self.assertEqual((Path(d) / "raw" / files[0]).read_bytes(), fetch_raw(files[0].split("_")[1]))

    def test_refuses_every_legacy_file(self):
        for legacy in collector.LEGACY_FILES:
            with self.subTest(file=legacy.name), self.assertRaises(SystemExit):
                collector.main(["--once", "--output", str(legacy)])

    def test_refuses_data_raw(self):
        with self.assertRaises(SystemExit):
            collector.check_output(ROOT / "data" / "raw" / "cita" / "new.csv")

    def test_refuses_existing_file_with_other_schema(self):
        with tempfile.TemporaryDirectory() as d:
            other = Path(d) / "other.csv"
            other.write_text("a;b;c\n1;2;3\n", encoding="utf-8")
            with self.assertRaises(SystemExit):
                collector.collect_once(other, set(), fetch=fetch_raw)
            self.assertEqual(other.read_text(encoding="utf-8"), "a;b;c\n1;2;3\n")   # untouched


if __name__ == "__main__":
    unittest.main()
