"""Turn-based simulation of the drone fleet."""

from __future__ import annotations

from models import Connection, Drone, Network, Zone
from pathfinder import Path

DEADLOCK_MESSAGE = "simulation stalled: no drone could move this turn"


class SimulationError(Exception):
    """Raised when the fleet cannot be routed to the end hub."""


class Simulator:
    """Move every drone from the start hub to the end hub, turn by turn."""

    def __init__(self, network: Network, plan: list[Path]) -> None:
        """Bind the simulator to a network and one path per drone."""
        self._net = network
        self._drones = network.spawn_drones()
        if len(plan) != len(self._drones):
            raise SimulationError(
                f"plan covers {len(plan)} drones "
                f"but {len(self._drones)} were requested"
            )
        for drone, path in zip(self._drones, plan):
            drone.assign(list(path.zones))
        self._occupancy: dict[str, int] = {
            name: 0 for name in network.zones
        }
        self._occupancy[network.start.name] = len(self._drones)
        self._load: dict[frozenset[str], int] = {
            link.key: 0 for link in network.connections
        }
        self._turns: list[list[str]] = []
        self._released: list[frozenset[str]] = []

    @property
    def turns(self) -> list[list[str]]:
        """The movements performed on each simulation turn."""
        return self._turns

    @property
    def total_turns(self) -> int:
        """Number of turns the simulation took."""
        return len(self._turns)

    def run(self) -> list[list[str]]:
        """Run the whole simulation and return its turns."""
        self._turns = []
        while not self._all_delivered():
            moves = self._play_turn()
            if not moves:
                raise SimulationError(DEADLOCK_MESSAGE)
            self._turns.append(moves)
        return self._turns

    def _all_delivered(self) -> bool:
        """Whether every drone has reached the end hub."""
        return all(drone.is_delivered for drone in self._drones)

    def _play_turn(self) -> list[str]:
        """Advance the whole fleet by one turn."""
        moves: list[str] = []
        self._released = []
        acted = {
            drone.id for drone in self._drones if drone.is_flying
        }
        for drone in self._drones:
            if drone.is_flying:
                moves.append(self._tick(drone))
        for drone in self._ready_drones():
            if drone.id in acted:
                continue
            move = self._try_move(drone)
            if move is not None:
                moves.append(move)
        for key in self._released:
            self._load[key] -= 1
        return moves

    def _ready_drones(self) -> list[Drone]:
        """Grounded, undelivered drones, the most advanced ones first."""
        waiting = [
            drone
            for drone in self._drones
            if not drone.is_flying and not drone.is_delivered
        ]
        return sorted(waiting, key=lambda drone: (-drone.step, drone.id))

    def _try_move(self, drone: Drone) -> str | None:
        """Send a drone to its next zone, or None if it must wait."""
        target = drone.next_zone
        if target is None:
            return None
        link = self._net.link_between(drone.position.name, target.name)
        if link is None or not self._can_enter(target, link):
            return None
        return self._depart(drone, link, target)

    def _can_enter(self, target: Zone, link: Connection) -> bool:
        """Whether the target zone and its link both have room."""
        if not target.is_accessible:
            return False
        if self._occupancy[target.name] >= target.capacity:
            return False
        return self._load[link.key] < link.capacity

    def _depart(self, drone: Drone, link: Connection, target: Zone) -> str:
        """Move a drone onto a link, reserving its destination."""
        self._occupancy[drone.position.name] -= 1
        self._occupancy[target.name] += 1
        self._load[link.key] += 1
        drone.depart(link, target.move_cost)
        return self._tick(drone)

    def _tick(self, drone: Drone) -> str:
        """Consume one turn of travel and report where the drone is."""
        link = drone.transit_link
        target = drone.next_zone
        if link is None or target is None:
            raise SimulationError(f"{drone.label} is in an invalid state")
        drone.turns_left -= 1
        if drone.turns_left > 0:
            return f"{drone.label}-{link.name}"
        self._released.append(link.key)
        drone.arrive(target)
        return f"{drone.label}-{target.name}"

    def report(self) -> str:
        """Return the turn lines in the format required by the subject."""
        return "\n".join(" ".join(moves) for moves in self._turns)

    def metrics(self) -> dict[str, float]:
        """Secondary metrics, useful when comparing two solutions."""
        moved = sum(len(moves) for moves in self._turns)
        drones = len(self._drones) or 1
        return {
            "turns": float(self.total_turns),
            "movements": float(moved),
            "moves_per_turn": moved / (self.total_turns or 1),
            "turns_per_drone": moved / drones,
        }
