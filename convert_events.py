import xml.etree.ElementTree as ET
import pandas as pd
import os

f = "./data/raw/cita_events/situationrecord36.xml"

tree = ET.parse(f)
root = tree.getroot()

def clean(value):
    if value is None:
        return ""
    return " ".join(value.split())

rows = []

for record in root.iter():
    if record.tag.split("}")[-1] != "situationRecord":
        continue

    row = {
        "event_type": "",
        "creation_time": "",
        "start_time": "",
        "validity": "",
        "road": "",
        "destination": "",
        "latitude": "",
        "longitude": "",
        "impact": "",
        "probability": "",
        "safety_message": "",
        "lanes_restricted": "",
        "operational_lanes": "",
        "original_lanes": "",
        "length_affected": "",
        "comment": "",
        "location_description": ""
    }

    for e in record.iter():
        tag = e.tag.split("}")[-1]
        value = clean(e.text)

        if tag in ["constructionWorkType", "obstructionType", "trafficConstrictionType"]:
            if value:
                row["event_type"] = value

        elif tag == "situationRecordCreationTime":
            row["creation_time"] = value

        elif tag == "overallStartTime":
            row["start_time"] = value

        elif tag == "roadName":
            row["road"] = value

        elif tag == "roadDestination":
            row["destination"] = value

        elif tag == "latitude":
            row["latitude"] = value

        elif tag == "longitude":
            row["longitude"] = value

        elif tag == "impact":
            row["impact"] = value

        elif tag == "probabilityOfOccurrence":
            row["probability"] = value

        elif tag == "safetyRelatedMessage":
            row["safety_message"] = value

        elif tag == "numberOfLanesRestricted":
            row["lanes_restricted"] = value

        elif tag == "numberOfOperationalLanes":
            row["operational_lanes"] = value

        elif tag == "originalNumberOfLanes":
            row["original_lanes"] = value

        elif tag == "lengthAffected":
            row["length_affected"] = value

        elif tag in ["comment", "generalPublicComment"]:
            if value:
                row["comment"] = value

        elif tag == "locationDescription":
            row["location_description"] = value

    if any(row.values()):
        rows.append(row)

df = pd.DataFrame(rows)

os.makedirs("./data/processed", exist_ok=True)

output = "./data/processed/cita_events.csv"

df.to_csv(
    output,
    index=False,
    encoding="utf-8-sig"
)

print("========================================")
print("CITA EVENTS -> CSV")
print("========================================")
print("Nombre d'evenements :", len(df))
print("Nombre de colonnes :", len(df.columns))
print("\nColonnes :")
print(df.columns.tolist())
print("\nApercu :")
print(df.head(10).to_string(index=False))
print("\nFichier :", output)
