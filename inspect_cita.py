import xml.etree.ElementTree as ET
import glob
import os

files = glob.glob("./data/raw/cita/*.xml")

for f in files:
    print("\n========================================")
    print("FILE:", os.path.basename(f))
    print("SIZE:", os.path.getsize(f), "bytes")
    print("========================================")

    tree = ET.parse(f)
    root = tree.getroot()

    print("ROOT:", root.tag)

    tags = sorted(set(
        element.tag.split("}")[-1]
        for element in root.iter()
    ))

    print("NUMBER OF XML TAG TYPES:", len(tags))
    print("\nTAGS:")
    for tag in tags:
        print(" -", tag)
