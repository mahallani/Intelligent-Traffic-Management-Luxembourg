import xml.etree.ElementTree as ET

f = "./data/raw/cita/trafficstatus_a1.xml"

root = ET.parse(f).getroot()

for e in root.iter():
    if e.tag.split("}")[-1] == "measuredValue":
        print("========================================")
        print("STRUCTURE D'UN measuredValue")
        print("========================================")
        for child in e.iter():
            tag = child.tag.split("}")[-1]
            value = (child.text or "").strip()
            print(f"{tag:40} = {value}")
        break
