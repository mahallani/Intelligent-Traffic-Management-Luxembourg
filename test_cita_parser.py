import xml.etree.ElementTree as ET

f = "./data/raw/cita/trafficstatus_a1.xml"
root = ET.parse(f).getroot()

def tag(e):
    return e.tag.split("}")[-1]

def txt(e):
    return (e.text or "").strip()

for mv in root.iter():
    if tag(mv) != "measuredValue":
        continue

    row = {
        "measurement_site": "",
        "timestamp": "",
        "latitude": "",
        "longitude": "",
        "road": "",
        "speed_kmh": "",
        "occupancy_percent": "",
        "vehicle_flow": "",
        "vehicle_flow_rate": ""
    }

    for e in mv.iter():
        t = tag(e)
        v = txt(e)

        if t == "specificLocation" and not row["measurement_site"] and v:
            row["measurement_site"] = v

        elif t == "measurementTimeDefault":
            row["timestamp"] = v

        elif t == "latitude":
            row["latitude"] = v

        elif t == "longitude":
            row["longitude"] = v

        elif t == "roadNumber":
            row["road"] = v

        elif t == "speed" and v:
            row["speed_kmh"] = v

        elif t == "percentage" and v:
            row["occupancy_percent"] = v

        elif t == "vehicleFlowRate" and v:
            row["vehicle_flow_rate"] = v

        elif t == "vehicleFlow" and v:
            row["vehicle_flow"] = v

    print(row)
