"""Weighted pathfinding over the zone network."""

from __future__ import annotations

import heapq
from typing import Iterator

from models import Network, Zone, ZoneType


class NoRouteError(Exception):
    """Raised when no valid route exists from the start to the end hub."""


class Path:
    """An ordered list of zones, from the start hub to the end hub."""

    def __init__(self, zones: list[Zone]) -> None:
        """Build a path from an ordered list of zones."""
        self.zones = zones

    @property
    def cost(self) -> int:
        """Turns needed to fly the path alone, ignoring congestion."""
        return sum(zone.move_cost for zone in self.zones[1:])

    @property
    def intermediate(self) -> list[Zone]:
        """Every zone except the start and end hubs."""
        return self.zones[1:-1]

    @property
    def names(self) -> list[str]:
        """The zone names, in travel order."""
        return [zone.name for zone in self.zones]

    def __len__(self) -> int:
        """Number of zones on the path."""
        return len(self.zones)

    def __iter__(self) -> Iterator[Zone]:
        """Iterate over the zones in travel order."""
        return iter(self.zones)

    def __repr__(self) -> str:
        """Return a debug representation."""
        return f"Path({' -> '.join(self.names)}, cost={self.cost})"


class PathFinder:
    """Compute weighted shortest routes across a Network."""

    def __init__(self, network: Network) -> None:
        """Bind the finder to the network it searches."""
        self._net = network

    def shortest(
        self,
        excluded: frozenset[str] = frozenset(),
    ) -> Path | None:
        """Cheapest route from start to end"""
        start, end = self._net.start, self._net.end
        if not start.is_accessible or not end.is_accessible:
            return None
        best: dict[str, tuple[int, int]] = {start.name: (0, 0)}
        came_from: dict[str, str] = {}
        heap: list[tuple[int, int, str]] = [(0, 0, start.name)]
        while heap:
            cost, penalty, name = heapq.heappop(heap)
            if (cost, penalty) != best.get(name):
                continue
            if name == end.name:
                return self._rebuild(came_from, name)
            for link in self._net.connections_from(name):
                nxt = self._net.zone(link.other_end(name))
                if nxt.name in excluded or not nxt.is_accessible:
                    continue
                candidate = (
                    cost + nxt.move_cost,
                    penalty + self._penalty(nxt),
                )
                known = best.get(nxt.name)
                if known is None or candidate < known:
                    best[nxt.name] = candidate
                    came_from[nxt.name] = name
                    heapq.heappush(heap, (*candidate, nxt.name))
        return None

    def require_shortest(
        self,
        excluded: frozenset[str] = frozenset(),
    ) -> Path:
        """Like shortest, but raise NoRouteError instead of returning None."""
        path = self.shortest(excluded)
        if path is None:
            raise NoRouteError(
                f"no route from '{self._net.start.name}' "
                f"to '{self._net.end.name}'"
            )
        return path

    @staticmethod
    def _penalty(zone: Zone) -> int:
        """Tie-breaker cost: zero for priority zones, one otherwise."""
        return 0 if zone.zone_type is ZoneType.PRIORITY else 1

    def disjoint_paths(self) -> list[Path]:
        """Routes sharing no intermediate zone, cheapest first."""
        paths: list[Path] = []
        used: set[str] = set()
        seen: set[tuple[str, ...]] = set()
        while True:
            path = self.shortest(frozenset(used))
            if path is None or tuple(path.names) in seen:
                break
            seen.add(tuple(path.names))
            paths.append(path)
            used.update(zone.name for zone in path.intermediate)
        if not paths:
            raise NoRouteError(
                f"no route from '{self._net.start.name}' "
                f"to '{self._net.end.name}'"
            )
        return sorted(paths, key=lambda item: item.cost)

    @staticmethod
    def distribute(paths: list[Path], nb_drones: int) -> list[int]:
        """How many drones to send down each path, in path order."""
        counts = [0] * len(paths)
        for _ in range(nb_drones):
            chosen = min(
                range(len(paths)),
                key=lambda index: paths[index].cost + counts[index],
            )
            counts[chosen] += 1
        return counts

    @staticmethod
    def estimated_turns(paths: list[Path], counts: list[int]) -> int:
        """Turns the plan should take if nothing blocks the drones."""
        return max(
            (
                path.cost + count - 1
                for path, count in zip(paths, counts)
                if count
            ),
            default=0,
        )

    def plan(self) -> list[Path]:
        """Return the path assigned to each drone, D1 first."""
        paths = self.disjoint_paths()
        counts = self.distribute(paths, self._net.nb_drones)
        assignment: list[Path] = []
        for path, count in zip(paths, counts):
            assignment.extend([path] * count)
        return assignment

    def _rebuild(self, came_from: dict[str, str], end_name: str) -> Path:
        """Walk the predecessor map backwards into a Path."""
        names = [end_name]
        while names[-1] in came_from:
            names.append(came_from[names[-1]])
        names.reverse()
        return Path([self._net.zone(name) for name in names])
