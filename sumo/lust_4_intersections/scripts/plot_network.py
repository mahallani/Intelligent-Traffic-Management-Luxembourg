"""Draw a labelled map of the reduced Kirchberg network -> docs/kirchberg_4tls_map.png"""
import xml.etree.ElementTree as ET
from pathlib import Path
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import sumolib

HERE = Path(__file__).resolve().parents[1]
net = sumolib.net.readNet(str(HERE / "net" / "kirchberg_4tls.net.xml"), withPrograms=True)
fig, ax = plt.subplots(figsize=(11, 8))
for e in net.getEdges():
    xs, ys = zip(*e.getShape())
    avenue = "31070" in e.getID()
    ax.plot(xs, ys, color="#3b3b3b" if avenue else "#9a9a9a", lw=3.2 if avenue else 1.4, zorder=1)
for s in ET.parse(HERE / "additional" / "busstops_kirchberg.add.xml").getroot().iter("busStop"):
    lane = net.getLane(s.get("lane"))
    x, y = sumolib.geomhelper.positionAtShapeOffset(lane.getShape(), float(s.get("startPos")))
    ax.plot(x, y, "s", color="#1f6fd1", ms=6, zorder=3)
for t in net.getTrafficLights():
    x, y = net.getNode(t.getID()).getCoord()
    ax.plot(x, y, "o", color="#d62728", ms=13, zorder=4)
    ax.annotate(f"TLS {t.getID()}", (x, y), xytext=(10, -16), textcoords="offset points", fontsize=11,
                fontweight="bold", color="#d62728")
for n in net.getNodes():
    if n.getType() == "dead_end" or not n.getIncoming() or not n.getOutgoing():
        x, y = n.getCoord()
        ax.plot(x, y, "^", color="#2ca02c", ms=7, zorder=2)
ax.plot([], [], "o", color="#d62728", label="feu (4)")
ax.plot([], [], "s", color="#1f6fd1", label="arrêt de bus (11)")
ax.plot([], [], "^", color="#2ca02c", label="entrée / sortie du réseau")
ax.plot([], [], color="#3b3b3b", lw=3, label="avenue J.F. Kennedy (31070)")
ax.legend(loc="lower right")
ax.set_aspect("equal"); ax.set_xticks([]); ax.set_yticks([])
ax.set_title("LuST réduit - Kirchberg, 4 carrefours à feux (SO -> NE)")
x0, y0 = ax.get_xlim()[0], ax.get_ylim()[0]
ax.plot([x0 + 30, x0 + 230], [y0 + 30, y0 + 30], color="k", lw=2); ax.text(x0 + 30, y0 + 45, "200 m")
out = HERE / "docs" / "kirchberg_4tls_map.png"
fig.savefig(out, dpi=110, bbox_inches="tight")
print(out)
