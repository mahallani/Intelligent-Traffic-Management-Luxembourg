from pathlib import Path
import requests
import pandas as pd
import xml.etree.ElementTree as ET
from datetime import datetime
import time

ROOT = Path(__file__).resolve().parent

# ============================================================
# DOSSIERS
# ============================================================

BASE = ROOT / "data" / "historical" / "cita"

TRAFFIC_DIR = BASE / "traffic"
EVENTS_DIR = BASE / "events"
TRAVEL_DIR = BASE / "travel_time"

TRAFFIC_DIR.mkdir(parents=True, exist_ok=True)
EVENTS_DIR.mkdir(parents=True, exist_ok=True)
TRAVEL_DIR.mkdir(parents=True, exist_ok=True)

TRAFFIC_FILE = TRAFFIC_DIR / "cita_traffic_live.csv"
EVENTS_FILE = EVENTS_DIR / "cita_events_live.csv"
TRAVEL_FILE = TRAVEL_DIR / "cita_travel_time_live.csv"

# ============================================================
# URLS OFFICIELLES CITA
# ============================================================

TRAFFIC_URLS = {
    "A1": "https://www.cita.lu/info_trafic/datex/trafficstatus_a1",
    "A3": "https://www.cita.lu/info_trafic/datex/trafficstatus_a3",
    "A4": "https://www.cita.lu/info_trafic/datex/trafficstatus_a4",
    "A6": "https://www.cita.lu/info_trafic/datex/trafficstatus_a6",
    "A7": "https://www.cita.lu/info_trafic/datex/trafficstatus_a7",
    "A13": "https://www.cita.lu/info_trafic/datex/trafficstatus_a13",
    "B40": "https://www.cita.lu/info_trafic/datex/trafficstatus_b40",
}

EVENTS_URL = "https://www.cita.lu/info_trafic/datex/situationrecord36"

# Ancien endpoint officiel CITA pour les temps de parcours.
# Le collecteur teste plusieurs variantes afin de ne rien perdre
# si CITA change l'endpoint.
TRAVEL_URLS = [
    "https://www.cita.lu/info_trafic/datex/travelTime",
    "https://www.cita.lu/info_trafic/datex/traveltime",
    "https://www.cita.lu/info_trafic/datex/travel_time",
    "https://www.cita.lu/info_trafic/datex/traveltimes",
]

# ============================================================
# NAMESPACE DATEX
# ============================================================

NS = {
    "d": "http://datex2.eu/schema/2/2_0",
    "d3": "http://datex2.eu/schema/3/situation",
    "gml": "http://www.opengis.net/gml/3.2",
}

def clean_text(element):
    if element is None:
        return None
    return element.text.strip() if element.text else None

def find_text(root, names):
    for name in names:
        for elem in root.iter():
            if elem.tag.lower().endswith(name.lower()):
                value = clean_text(elem)
                if value:
                    return value
    return None

def find_all_text(parent, name):
    values = []
    for elem in parent.iter():
        if elem.tag.lower().endswith(name.lower()):
            value = clean_text(elem)
            if value:
                values.append(value)
    return values

# ============================================================
# TRAFFIC
# ============================================================

def collect_traffic():
    rows = []
    collection_time = datetime.now().isoformat()

    for road, url in TRAFFIC_URLS.items():

        try:
            r = requests.get(url, timeout=30)
            r.raise_for_status()

            root = ET.fromstring(r.content)

            for basic in root.iter():

                if not basic.tag.lower().endswith("basicdata"):
                    continue

                timestamp = find_text(
                    basic,
                    ["measurementTimeDefault"]
                )

                site = find_text(
                    basic,
                    ["measurementSiteReference"]
                )

                latitude = find_text(
                    basic,
                    ["latitude"]
                )

                longitude = find_text(
                    basic,
                    ["longitude"]
                )

                direction = find_text(
                    basic,
                    ["directionBoundOnLinearSection"]
                )

                speed = find_text(
                    basic,
                    ["speed"]
                )

                occupancy = find_text(
                    basic,
                    ["occupancy"]
                )

                flow_rate = find_text(
                    basic,
                    ["vehicleFlowRate"]
                )

                if speed is None:
                    speed = find_text(
                        basic,
                        ["averageVehicleSpeed"]
                    )

                if any([
                    timestamp,
                    site,
                    speed,
                    occupancy,
                    flow_rate
                ]):

                    rows.append({
                        "collection_time": collection_time,
                        "road": road,
                        "measurement_site": site,
                        "timestamp": timestamp,
                        "latitude": latitude,
                        "longitude": longitude,
                        "direction": direction,
                        "speed_kmh": speed,
                        "occupancy_percent": occupancy,
                        "vehicle_flow_rate": flow_rate
                    })

        except Exception as e:
            print(f"[TRAFFIC][{road}] ERREUR: {e}")

    if not rows:
        print("[TRAFFIC] aucune donnée.")
        return

    df = pd.DataFrame(rows)

    # conversions numériques
    for col in [
        "latitude",
        "longitude",
        "speed_kmh",
        "occupancy_percent",
        "vehicle_flow_rate"
    ]:
        df[col] = pd.to_numeric(df[col], errors="coerce")

    # éviter les doublons créés par les blocs DATEX imbriqués
    key = [
        "road",
        "measurement_site",
        "timestamp",
        "direction",
        "latitude",
        "longitude",
        "speed_kmh",
        "occupancy_percent",
        "vehicle_flow_rate"
    ]

    df = df.drop_duplicates(subset=key)

    if TRAFFIC_FILE.exists():
        old = pd.read_csv(TRAFFIC_FILE)
        df = pd.concat([old, df], ignore_index=True)

        df = df.drop_duplicates(
            subset=key,
            keep="last"
        )

    df.to_csv(
        TRAFFIC_FILE,
        index=False,
        encoding="utf-8"
    )

    print(
        f"[TRAFFIC] +{len(rows)} observations | "
        f"total={len(df)}"
    )

# ============================================================
# EVENTS
# ============================================================

def collect_events():

    rows = []
    collection_time = datetime.now().isoformat()

    try:
        r = requests.get(EVENTS_URL, timeout=30)
        r.raise_for_status()

        root = ET.fromstring(r.content)

        for record in root.iter():

            if not record.tag.lower().endswith("situationrecord"):
                continue

            event_type = record.attrib.get("xsi:type")

            if event_type is None:
                event_type = find_text(
                    record,
                    ["situationRecord"]
                )

            creation = find_text(
                record,
                ["situationRecordCreationTime"]
            )

            version = find_text(
                record,
                ["situationRecordVersionTime"]
            )

            start = find_text(
                record,
                ["overallStartTime"]
            )

            validity = find_text(
                record,
                ["validityStatus"]
            )

            road = find_text(
                record,
                ["roadNumber"]
            )

            destination = find_text(
                record,
                ["roadDestination"]
            )

            latitude = find_text(
                record,
                ["latitude"]
            )

            longitude = find_text(
                record,
                ["longitude"]
            )

            impact = find_text(
                record,
                ["impact"]
            )

            probability = find_text(
                record,
                ["probabilityOfOccurrence"]
            )

            safety = find_text(
                record,
                ["safetyRelatedMessage"]
            )

            lanes_restricted = find_text(
                record,
                ["numberOfLanesRestricted"]
            )

            operational_lanes = find_text(
                record,
                ["numberOfOperationalLanes"]
            )

            original_lanes = find_text(
                record,
                ["originalNumberOfLanes"]
            )

            length = find_text(
                record,
                ["lengthAffected"]
            )

            comment = find_text(
                record,
                ["generalPublicComment", "comment"]
            )

            rows.append({
                "collection_time": collection_time,
                "event_type": event_type,
                "creation_time": creation,
                "version_time": version,
                "start_time": start,
                "validity": validity,
                "road": road,
                "destination": destination,
                "latitude": latitude,
                "longitude": longitude,
                "impact": impact,
                "probability": probability,
                "safety_message": safety,
                "lanes_restricted": lanes_restricted,
                "operational_lanes": operational_lanes,
                "original_lanes": original_lanes,
                "length_affected": length,
                "comment": comment
            })

    except Exception as e:
        print(f"[EVENTS] ERREUR: {e}")
        return

    if not rows:
        print("[EVENTS] aucune donnée.")
        return

    df = pd.DataFrame(rows)

    for col in [
        "latitude",
        "longitude",
        "lanes_restricted",
        "operational_lanes",
        "original_lanes",
        "length_affected"
    ]:
        df[col] = pd.to_numeric(
            df[col],
            errors="coerce"
        )

    if EVENTS_FILE.exists():
        old = pd.read_csv(EVENTS_FILE)
        df = pd.concat(
            [old, df],
            ignore_index=True
        )

    df.to_csv(
        EVENTS_FILE,
        index=False,
        encoding="utf-8"
    )

    print(
        f"[EVENTS] +{len(rows)} événements | "
        f"total={len(df)}"
    )

# ============================================================
# TRAVEL TIME
# ============================================================

def collect_travel_time():

    success = False

    for url in TRAVEL_URLS:

        try:
            r = requests.get(
                url,
                timeout=20
            )

            if r.status_code != 200:
                continue

            root = ET.fromstring(r.content)

            rows = []

            for elem in root.iter():

                tag = elem.tag.lower()

                if (
                    tag.endswith("travelTime")
                    or tag.endswith("travelTimeValue")
                    or tag.endswith("travelTimeData")
                ):

                    row = {
                        "collection_time": datetime.now().isoformat(),
                        "element": tag,
                        "value": clean_text(elem)
                    }

                    rows.append(row)

            if rows:

                df = pd.DataFrame(rows)

                if TRAVEL_FILE.exists():
                    old = pd.read_csv(TRAVEL_FILE)
                    df = pd.concat(
                        [old, df],
                        ignore_index=True
                    )

                df.to_csv(
                    TRAVEL_FILE,
                    index=False,
                    encoding="utf-8"
                )

                print(
                    f"[TRAVEL TIME] +{len(rows)} observations"
                )

                success = True
                break

        except Exception:
            continue

    if not success:
        print(
            "[TRAVEL TIME] endpoint non trouvé "
            "dans les variantes testées."
        )

# ============================================================
# MAIN
# ============================================================

print("=" * 70)
print(" LUXEMBOURG TRAFFIC DATA COLLECTOR")
print("=" * 70)
print()
print("Sources:")
print("  - CITA Traffic : A1 A3 A4 A6 A7 A13 B40")
print("  - CITA Events v3.6")
print("  - CITA Travel Time")
print()
print("Intervalle : 60 secondes")
print("Arrêt : CTRL+C")
print()

while True:

    print()
    print(
        "=" * 70
    )

    print(
        datetime.now().strftime(
            "%Y-%m-%d %H:%M:%S"
        )
    )

    collect_traffic()
    collect_events()
    collect_travel_time()

    print()
    print("Prochaine collecte dans 60 secondes...")

    time.sleep(60)
