import xml.etree.ElementTree as ET

f = "./data/raw/cita_events/situationrecord36.xml"

tree = ET.parse(f)
root = tree.getroot()

tags = sorted(set(
    element.tag.split("}")[-1]
    for element in root.iter()
))

print("========================================")
print("CITA EVENTS v3.6")
print("========================================")
print("Fichier :", f)
print("Nombre total de balises :", sum(1 for _ in root.iter()))
print("Nombre de types de balises :", len(tags))

print("\nTYPES DE BALISES :")
for i, tag in enumerate(tags, 1):
    print(f"{i:03d}. {tag}")
