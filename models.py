from __future__ import annotations

import sys
from enum import Enum

UNLIMITED = sys.maxsize


class ZoneType(Enum):
    """The four zone categories defined by the subject."""

    NORMAL = "normal"
    BLOCKED = "blocked"
    RESTRICTED = "restricted"
    PRIORITY = "priority"

    @classmethod
    def from_string(cls, raw: str) -> "ZoneType":
        """Return the member whose value is raw, or raise ValueError."""
        for member in cls:
            if member.value == raw:
                return member
        valid = ", ".join(member.value for member in cls)
        raise ValueError(
            f"unknown zone type '{raw}' (expected one of: {valid})"
        )

    @property
    def move_cost(self) -> int:
        """Turns needed to move into a zone of this type."""
        return 2 if self is ZoneType.RESTRICTED else 1

    @property
    def is_accessible(self) -> bool:
        """Whether a drone may enter this kind of zone."""
        return self is not ZoneType.BLOCKED


class Zone:
    """A single zone (node) of the network."""

    def __init__(
        self,
        name: str,
        x: int,
        y: int,
        zone_type: ZoneType = ZoneType.NORMAL,
        color: str | None = None,
        max_drones: int = 1,
        is_start: bool = False,
        is_end: bool = False,
    ) -> None:
        """Build a zone from its parsed fields and metadata."""
        self.name = name
        self.x = x
        self.y = y
        self.zone_type = zone_type
        self.color = color
        self.is_start = is_start
        self.is_end = is_end
        self._max_drones = max_drones

    @property
    def capacity(self) -> int:
        """Occupancy limit; the start and end hubs are unlimited."""
        if self.is_start or self.is_end:
            return UNLIMITED
        return self._max_drones

    @property
    def move_cost(self) -> int:
        """Turns needed to enter this zone."""
        return self.zone_type.move_cost

    @property
    def is_accessible(self) -> bool:
        """Whether drones may enter this zone."""
        return self.zone_type.is_accessible

    def __repr__(self) -> str:
        """Return a debug representation."""
        return (
            f"Zone({self.name!r}, {self.x}, {self.y}, "
            f"{self.zone_type.value}, capacity={self.capacity})"
        )


class Connection:
    """A bidirectional link between two zones."""

    def __init__(
        self,
        first: str,
        second: str,
        max_link_capacity: int = 1,
    ) -> None:
        """Build a link between two zone names, in declaration order."""
        self.first = first
        self.second = second
        self.capacity = max_link_capacity

    @property
    def name(self) -> str:
        """Displayed name, used while a drone is in transit."""
        return f"{self.first}-{self.second}"

    @property
    def key(self) -> frozenset[str]:
        """Order-independent identity, so a-b equals b-a."""
        return frozenset((self.first, self.second))

    def other_end(self, zone_name: str) -> str:
        """Return the endpoint opposite to zone_name, or raise KeyError."""
        if zone_name == self.first:
            return self.second
        if zone_name == self.second:
            return self.first
        raise KeyError(f"'{zone_name}' is not an endpoint of {self.name}")

    def __repr__(self) -> str:
        """Return a debug representation."""
        return f"Connection({self.name!r}, capacity={self.capacity})"


class Drone:
    """A single drone and everything the simulator needs to track it."""

    def __init__(self, identifier: int, position: Zone) -> None:
        """Create drone number identifier, parked on the start hub."""
        self.id = identifier
        self.position = position
        self.route: list[Zone] = []
        self.step = 0
        self.transit_link: Connection | None = None
        self.turns_left = 0

    @property
    def label(self) -> str:
        """Identifier as printed in the output, e.g. 'D1'."""
        return f"D{self.id}"

    @property
    def is_flying(self) -> bool:
        """Whether the drone is currently on a connection."""
        return self.transit_link is not None

    @property
    def is_delivered(self) -> bool:
        """Whether the drone has reached the end hub."""
        return self.position.is_end and not self.is_flying

    @property
    def next_zone(self) -> Zone | None:
        """The next zone on the assigned route, if any."""
        if self.step + 1 < len(self.route):
            return self.route[self.step + 1]
        return None

    def assign(self, route: list[Zone]) -> None:
        """Give the drone a route starting at its current zone."""
        self.route = route
        self.step = 0

    def depart(self, link: Connection, cost: int) -> None:
        """Send the drone onto link for cost turns of travel."""
        self.transit_link = link
        self.turns_left = cost

    def arrive(self, zone: Zone) -> None:
        """Land the drone in zone and clear its transit state."""
        self.position = zone
        self.transit_link = None
        self.turns_left = 0
        self.step += 1

    def __repr__(self) -> str:
        """Return a debug representation."""
        where = self.transit_link.name if self.transit_link else (
            self.position.name
        )
        return f"Drone({self.label}, at={where})"


class Network:
    """The whole map: zones, connections and adjacency."""

    def __init__(self, nb_drones: int) -> None:
        """Build an empty network for nb_drones drones."""
        self.nb_drones = nb_drones
        self.zones: dict[str, Zone] = {}
        self.connections: list[Connection] = []
        self._adjacency: dict[str, list[Connection]] = {}
        self._start: Zone | None = None
        self._end: Zone | None = None

    @property
    def start(self) -> Zone:
        """The start hub, or raise ValueError if undefined."""
        if self._start is None:
            raise ValueError("network has no start hub")
        return self._start

    @property
    def end(self) -> Zone:
        """The end hub, or raise ValueError if undefined."""
        if self._end is None:
            raise ValueError("network has no end hub")
        return self._end

    @property
    def has_start(self) -> bool:
        """Whether a start hub has been registered."""
        return self._start is not None

    @property
    def has_end(self) -> bool:
        """Whether an end hub has been registered."""
        return self._end is not None

    def has_zone(self, name: str) -> bool:
        """Whether a zone named name exists."""
        return name in self.zones

    def zone(self, name: str) -> Zone:
        """Return the zone named name, or raise KeyError."""
        return self.zones[name]

    def add_zone(self, zone: Zone) -> None:
        """Register a zone, raising KeyError on a duplicate name."""
        if zone.name in self.zones:
            raise KeyError(f"duplicate zone name '{zone.name}'")
        self.zones[zone.name] = zone
        self._adjacency[zone.name] = []
        if zone.is_start:
            self._start = zone
        if zone.is_end:
            self._end = zone

    def add_connection(self, connection: Connection) -> None:
        """Register a link between two known zones, both ways."""
        for endpoint in (connection.first, connection.second):
            if endpoint not in self.zones:
                raise KeyError(f"unknown zone '{endpoint}'")
        self.connections.append(connection)
        self._adjacency[connection.first].append(connection)
        self._adjacency[connection.second].append(connection)

    def connections_from(self, name: str) -> list[Connection]:
        """Every connection touching the zone named name."""
        return self._adjacency.get(name, [])

    def link_between(self, first: str, second: str) -> Connection | None:
        """The connection joining two zones, or None if unlinked."""
        for link in self.connections_from(first):
            if link.other_end(first) == second:
                return link
        return None

    def neighbours(self, name: str) -> list[Zone]:
        """The zones directly reachable from name."""
        return [
            self.zones[link.other_end(name)]
            for link in self.connections_from(name)
        ]

    def spawn_drones(self) -> list[Drone]:
        """Create every drone, parked on the start hub."""
        return [
            Drone(number, self.start)
            for number in range(1, self.nb_drones + 1)
        ]

    def __repr__(self) -> str:
        """Return a debug representation."""
        return (
            f"Network(nb_drones={self.nb_drones}, "
            f"zones={len(self.zones)}, links={len(self.connections)})"
        )
