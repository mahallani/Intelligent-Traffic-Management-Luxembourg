import xml.etree.ElementTree as ET
import pandas as pd
import glob
import os

files = glob.glob("./data/raw/cita/trafficstatus_*.xml")
rows = []

for file in files:
    road_file = os.path.basename(file).replace("trafficstatus_", "").replace(".xml", "").upper()
    root = ET.parse(file).getroot()

    for site in root.iter():
        if site.tag.split("}")[-1] != "siteMeasurements":
            continue

        row = {
            "road": road_file,
            "measurement_site": "",
            "timestamp": "",
            "latitude": "",
            "longitude": "",
            "speed_kmh": "",
            "occupancy_percent": "",
            "vehicle_flow": "",
            "vehicle_flow_rate": ""
        }

        for parent in site.iter():
            tag = parent.tag.split("}")[-1]
            value = parent.text.strip() if parent.text and parent.text.strip() else None

            if tag == "measurementSiteReference" and value:
                row["measurement_site"] = value

            elif tag == "measurementTimeDefault" and value:
                row["timestamp"] = value

            elif tag == "latitude" and value:
                row["latitude"] = value

            elif tag == "longitude" and value:
                row["longitude"] = value

            elif tag == "averageVehicleSpeed" and value:
                row["speed_kmh"] = value

            elif tag == "occupancy" and value:
                row["occupancy_percent"] = value

            elif tag == "vehicleFlow" and value:
                row["vehicle_flow"] = value

            elif tag == "vehicleFlowRate" and value:
                row["vehicle_flow_rate"] = value

        if any(row[k] != "" for k in [
            "speed_kmh",
            "occupancy_percent",
            "vehicle_flow",
            "vehicle_flow_rate"
        ]):
            rows.append(row)

df = pd.DataFrame(rows)

os.makedirs("./data/processed", exist_ok=True)

output = "./data/processed/cita_traffic.csv"
df.to_csv(output, index=False, encoding="utf-8-sig")

print("========================================")
print("CITA XML -> CSV TERMINE")
print("========================================")
print("Nombre de lignes :", len(df))
print("Nombre de colonnes :", len(df.columns))
print("\nColonnes :")
print(df.columns.tolist())
print("\nPremieres lignes :")
print(df.head(10).to_string(index=False))
print("\nFichier cree :", output)
