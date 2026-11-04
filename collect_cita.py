import requests
import xml.etree.ElementTree as ET
import pandas as pd
import os
import time
from datetime import datetime

BASE = "./data/historical/cita"
os.makedirs(BASE + "/traffic", exist_ok=True)
os.makedirs(BASE + "/events", exist_ok=True)

ROADS = ["a1", "a3", "a4", "a6", "a7", "a13", "b40"]

TRAFFIC_URL = "https://www.cita.lu/info_trafic/datex/trafficstatus_{}"
EVENTS_URL = "https://cita.lu/info_trafic/datex/situationrecord36"

def tag(e):
    return e.tag.split("}")[-1]

def text(e):
    return (e.text or "").strip()

def collect_traffic():

    rows = []

    for road in ROADS:

        try:
            url = TRAFFIC_URL.format(road)
            response = requests.get(url, timeout=30)
            response.raise_for_status()

            root = ET.fromstring(response.content)

            for site in root.iter():

                if tag(site) != "siteMeasurements":
                    continue

                row = {
                    "collection_time": datetime.now().isoformat(),
                    "road": road.upper(),
                    "measurement_site": "",
                    "timestamp": "",
                    "latitude": "",
                    "longitude": "",
                    "speed_kmh": "",
                    "occupancy_percent": "",
                    "vehicle_flow": "",
                    "vehicle_flow_rate": ""
                }

                for e in site.iter():

                    t = tag(e)
                    v = text(e)

                    if not v:
                        continue

                    if t == "measurementSiteReference":
                        row["measurement_site"] = v

                    elif t == "measurementTimeDefault":
                        row["timestamp"] = v

                    elif t == "latitude":
                        row["latitude"] = v

                    elif t == "longitude":
                        row["longitude"] = v

                    elif t == "averageVehicleSpeed":
                        row["speed_kmh"] = v

                    elif t == "occupancy":
                        row["occupancy_percent"] = v

                    elif t == "vehicleFlow":
                        row["vehicle_flow"] = v

                    elif t == "vehicleFlowRate":
                        row["vehicle_flow_rate"] = v

                rows.append(row)

        except Exception as e:
            print("Traffic error", road, ":", e)

    if rows:

        df = pd.DataFrame(rows)

        file = BASE + "/traffic/cita_traffic_historical.csv"

        df.to_csv(
            file,
            mode="a",
            header=not os.path.exists(file),
            index=False,
            encoding="utf-8-sig"
        )

        print("Traffic:", len(df), "mesures")

def collect_events():

    try:

        response = requests.get(EVENTS_URL, timeout=30)
        response.raise_for_status()

        root = ET.fromstring(response.content)

        rows = []

        for record in root.iter():

            if tag(record) != "situationRecord":
                continue

            row = {
                "collection_time": datetime.now().isoformat(),
                "event_type": "",
                "creation_time": "",
                "start_time": "",
                "road": "",
                "destination": "",
                "latitude": "",
                "longitude": "",
                "impact": "",
                "probability": "",
                "lanes_restricted": "",
                "operational_lanes": "",
                "original_lanes": "",
                "length_affected": "",
                "comment": "",
                "location_description": ""
            }

            for e in record.iter():

                t = tag(e)
                v = text(e)

                if not v:
                    continue

                if t in [
                    "constructionWorkType",
                    "obstructionType",
                    "trafficConstrictionType"
                ]:
                    row["event_type"] = v

                elif t == "situationRecordCreationTime":
                    row["creation_time"] = v

                elif t == "overallStartTime":
                    row["start_time"] = v

                elif t == "roadName":
                    row["road"] = v

                elif t == "roadDestination":
                    row["destination"] = v

                elif t == "latitude":
                    row["latitude"] = v

                elif t == "longitude":
                    row["longitude"] = v

                elif t == "impact":
                    row["impact"] = v

                elif t == "probabilityOfOccurrence":
                    row["probability"] = v

                elif t == "numberOfLanesRestricted":
                    row["lanes_restricted"] = v

                elif t == "numberOfOperationalLanes":
                    row["operational_lanes"] = v

                elif t == "originalNumberOfLanes":
                    row["original_lanes"] = v

                elif t == "lengthAffected":
                    row["length_affected"] = v

                elif t in ["comment", "generalPublicComment"]:
                    row["comment"] = v

                elif t == "locationDescription":
                    row["location_description"] = v

            rows.append(row)

        if rows:

            df = pd.DataFrame(rows)

            file = BASE + "/events/cita_events_historical.csv"

            df.to_csv(
                file,
                mode="a",
                header=not os.path.exists(file),
                index=False,
                encoding="utf-8-sig"
            )

            print("Events:", len(df))

    except Exception as e:
        print("Events error:", e)

print("==========================================")
print(" CITA HISTORICAL COLLECTOR")
print("==========================================")
print("Collection toutes les 60 secondes")
print("CTRL+C pour arreter")
print()

while True:

    start = time.time()

    print(
        "\nCollection:",
        datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    )

    collect_traffic()
    collect_events()

    elapsed = time.time() - start
    wait = max(0, 60 - elapsed)

    print("Prochaine collecte dans", round(wait), "secondes")

    time.sleep(wait)
