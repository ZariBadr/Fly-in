"""Command line entry point for the Fly-in drone routing simulation."""

from __future__ import annotations

import argparse
import os
import re
import sys

from map_parser import MapParser, ParseError
from pathfinder import NoRouteError, Path, PathFinder
from simulator import SimulationError, Simulator

EXIT_OK = 0
EXIT_ERROR = 1

RESET = "\033[0m"
BOLD = "\033[1m"
DIM = "\033[2m"

#: Color names accepted in the ``color=<value>`` metadata.
NAMED_COLORS: dict[str, int] = {
    "black": 240, "gray": 244, "grey": 244, "silver": 250, "white": 255,
    "red": 196, "maroon": 124, "salmon": 209, "orange": 208, "gold": 220,
    "brown": 130, "yellow": 226, "olive": 142, "lime": 118, "green": 46,
    "teal": 37, "cyan": 51, "aqua": 45, "blue": 33, "navy": 27,
    "indigo": 93, "purple": 129, "violet": 177, "magenta": 201,
    "pink": 213,
}

#: Readable colors used for a color name that is not in the table.
FALLBACK_COLORS: tuple[int, ...] = (
    39, 45, 51, 78, 84, 114, 120, 156, 178, 184,
    190, 202, 208, 214, 219, 141, 135, 105, 99, 75,
)

#: Color of a zone that declares no color, based on its type.
TYPE_COLORS: dict[str, int] = {
    "normal": 252,
    "priority": 51,
    "restricted": 203,
    "blocked": 240,
}

#: Colors cycled through for the drones themselves.
DRONE_COLORS: tuple[int, ...] = (
    45, 214, 118, 201, 220, 51, 208, 141, 84, 213,
    39, 190, 171, 78, 203, 111, 156, 227, 99, 44,
)


class Palette:
    """Colors the simulation 
    """

    _ZONE_RE = re.compile(
        r"^(?P<kind>start_hub|end_hub|hub)\s*:\s+(?P<name>\S+)"
        r"(?:[^\[\]]*\[(?P<meta>[^\]]*)\])?"
    )
    _TAG_RE = re.compile(r"(?P<key>\w+)=(?P<value>\S+)")

    def __init__(self, enabled: bool = True) -> None:
        """Create an empty palette.

        Args:
            enabled: When ``False`` every method returns plain text.
        """
        self.enabled = enabled
        self._zones: dict[str, str] = {}

    @classmethod
    def from_map(cls, path: str, enabled: bool) -> "Palette":
        """Build a palette by reading the zones of a map file.

        Args:
            path: Path of the map file being simulated.
            enabled: Whether colors should be emitted at all.

        Returns:
            A palette; an empty one if the file cannot be read again,
            since colors must never break the simulation.
        """
        palette = cls(enabled)
        if not enabled:
            return palette
        try:
            with open(path, "r", encoding="utf-8") as stream:
                for line in stream:
                    palette._read_zone(line)
        except OSError:
            pass
        return palette

    def _read_zone(self, line: str) -> None:
        """Record the color of a single zone definition line."""
        match = self._ZONE_RE.match(line.split("#", 1)[0].strip())
        if match is None:
            return
        tags = {
            tag.group("key"): tag.group("value")
            for tag in self._TAG_RE.finditer(match.group("meta") or "")
        }
        color = self._index(tags.get("color"), tags.get("zone", "normal"))
        style = BOLD if match.group("kind") != "hub" else ""
        self._zones[match.group("name")] = f"{style}\033[38;5;{color}m"

    @staticmethod
    def _index(color: str | None, zone_type: str) -> int:
        """Return the 256-color index of a zone.

        An explicit color wins; any single word is accepted, unknown
        ones get a stable color derived from the word itself.  Without
        a color, the type of the zone decides.
        """
        if color is None:
            return TYPE_COLORS.get(zone_type, TYPE_COLORS["normal"])
        lowered = color.lower()
        if lowered in NAMED_COLORS:
            return NAMED_COLORS[lowered]
        digest = sum(
            (position + 1) * ord(char)
            for position, char in enumerate(lowered)
        )
        return FALLBACK_COLORS[digest % len(FALLBACK_COLORS)]

    # -- painting ------------------------------------------------------
    def zone(self, name: str) -> str:
        """Paint a zone name with its own color."""
        if not self.enabled:
            return name
        style = self._zones.get(name)
        if style is None:
            return name
        return f"{style}{name}{RESET}"

    def drone(self, name: str) -> str:
        """Paint a drone identifier such as ``D7``."""
        if not self.enabled or not name[1:].isdigit():
            return name
        color = DRONE_COLORS[(int(name[1:]) - 1) % len(DRONE_COLORS)]
        return f"{BOLD}\033[38;5;{color}m{name}{RESET}"

    def dim(self, text: str) -> str:
        """Dim a piece of text, used for drones still in flight."""
        if not self.enabled:
            return text
        return f"{DIM}{text}{RESET}"

    def colorize(self, report: str) -> str:
        """Color a whole simulation
        """
        if not self.enabled or not self._zones:
            return report
        lines = (
            " ".join(self._token(token) for token in line.split(" "))
            for line in report.split("\n")
        )
        return "\n".join(lines)

    def _token(self, token: str) -> str:
        """Color a single ``D<id>-<destination>`` movement token."""
        drone, separator, target = token.partition("-")
        if not separator or not drone.startswith("D"):
            return token
        if target in self._zones:
            return f"{self.drone(drone)}-{self.zone(target)}"
        # Zone names cannot contain a dash, so anything left is the
        # name of a connection: the drone is still in flight.
        return f"{self.drone(drone)}-{self.dim(target)}"


class Application:
    """Parse a map, plan the routes and run the simulation."""

    def __init__(self, argv: list[str] | None = None) -> None:
        """Read the command line arguments."""
        self._args = self._build_parser().parse_args(argv)
        self._palette = Palette(False)

    @staticmethod
    def _build_parser() -> argparse.ArgumentParser:
        """Describe the accepted command line arguments."""
        parser = argparse.ArgumentParser(
            prog="fly-in",
            description="Route a fleet of drones through a zone network.",
        )
        parser.add_argument("map", help="path to the map file")
        parser.add_argument(
            "-p",
            "--paths",
            action="store_true",
            help="show the routes chosen before the simulation",
        )
        parser.add_argument(
            "-m",
            "--metrics",
            action="store_true",
            help="show secondary metrics after the simulation",
        )
        parser.add_argument(
            "-c",
            "--no-color",
            action="store_true",
            help="never colorize the output",
        )
        return parser

    def _wants_color(self) -> bool:
        """Whether the output should be colorized.

        Colors are dropped when the user asks for it, when ``NO_COLOR``
        is set, and when the output is redirected, so a piped or saved
        run stays perfectly plain.
        """
        if self._args.no_color or os.environ.get("NO_COLOR") is not None:
            return False
        if os.environ.get("TERM", "") == "dumb":
            return False
        return sys.stdout.isatty()

    def run(self) -> int:
        """Run the whole pipeline and return a process exit code."""
        try:
            network = MapParser(self._args.map).parse()
            self._palette = Palette.from_map(
                self._args.map, self._wants_color()
            )
            finder = PathFinder(network)
            paths = finder.disjoint_paths()
            counts = finder.distribute(paths, network.nb_drones)
            if self._args.paths:
                self._show_paths(finder, paths, counts)
            simulator = Simulator(network, finder.plan())
            simulator.run()
            print(self._palette.colorize(simulator.report()))
            if self._args.metrics:
                self._show_metrics(simulator)
        except (ParseError, NoRouteError, SimulationError) as error:
            print(f"error: {error}", file=sys.stderr)
            return EXIT_ERROR
        except KeyboardInterrupt:
            print("interrupted", file=sys.stderr)
            return EXIT_ERROR
        except BrokenPipeError:
            sys.stderr.close()
            return EXIT_OK
        return EXIT_OK

    def _show_paths(
        self,
        finder: PathFinder,
        paths: list[Path],
        counts: list[int],
    ) -> None:
        """Print the planned routes and the expected turn count."""
        for path, count in zip(paths, counts):
            route = " -> ".join(
                self._palette.zone(name) for name in path.names
            )
            print(
                f"# {count} drone(s) | cost {path.cost} | {route}",
                file=sys.stderr,
            )
        print(
            f"# estimated turns: {finder.estimated_turns(paths, counts)}",
            file=sys.stderr,
        )

    @staticmethod
    def _show_metrics(simulator: Simulator) -> None:
        """Print the secondary metrics of a finished simulation."""
        for label, value in simulator.metrics().items():
            print(f"# {label}: {value:.2f}", file=sys.stderr)


def main() -> int:
    """Build the application and run it."""
    return Application().run()


if __name__ == "__main__":
    sys.exit(main())
