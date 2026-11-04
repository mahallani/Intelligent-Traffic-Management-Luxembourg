"""
Static network topology (edge adjacency) read from ``lust.net.xml``.

Used for congestion propagation (Cascade Agent): which edges feed which edges.
Parsed once with a streaming XML parser (``<connection from=.. to=..>`` elements),
so no TraCI call is needed and memory stays low (~10 MB net file).
"""
from __future__ import annotations

import xml.etree.ElementTree as ET
from collections import defaultdict
from pathlib import Path

from .config import _read_cfg_list


class NetworkTopology:
    """Edge-to-edge adjacency of a SUMO network (internal edges excluded)."""

    def __init__(self, net_file: Path | str):
        self.net_file = Path(net_file)
        self._down: dict[str, set[str]] = defaultdict(set)
        self._up: dict[str, set[str]] = defaultdict(set)
        for _, el in ET.iterparse(self.net_file, events=("end",)):
            if el.tag == "connection":
                a, b = el.get("from", ""), el.get("to", "")
                if a and b and not a.startswith(":") and not b.startswith(":"):
                    self._down[a].add(b)
                    self._up[b].add(a)
            el.clear()

    @classmethod
    def from_sumocfg(cls, sumocfg: Path | str) -> "NetworkTopology":
        sumocfg = Path(sumocfg)
        net = _read_cfg_list(sumocfg, "net-file")[0]
        return cls(sumocfg.parent / net)

    def downstream(self, edge_id: str) -> set[str]:
        """Edges a vehicle can enter after ``edge_id``."""
        return self._down.get(edge_id, set())

    def upstream(self, edge_id: str) -> set[str]:
        """Edges feeding ``edge_id`` (where its queue spills back)."""
        return self._up.get(edge_id, set())

    def upstream_within(self, edge_id: str, depth: int = 2) -> set[str]:
        """All edges up to ``depth`` hops upstream (spill-back zone)."""
        seen, frontier = set(), {edge_id}
        for _ in range(depth):
            frontier = {u for e in frontier for u in self.upstream(e)} - seen - {edge_id}
            seen |= frontier
        return seen
