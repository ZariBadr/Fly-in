"""Command line entry point for the Fly-in drone routing simulation."""

from __future__ import annotations

import argparse
import sys

from map_parser import MapParser, ParseError
from pathfinder import NoRouteError, Path, PathFinder
from simulator import SimulationError, Simulator

EXIT_OK = 0
EXIT_ERROR = 1


class Application:
    """Parse a map, plan the routes and run the simulation."""

    def __init__(self, argv: list[str] | None = None) -> None:
        """Read the command line arguments."""
        self._args = self._build_parser().parse_args(argv)

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
        return parser

    def run(self) -> int:
        """Run the whole pipeline and return a process exit code."""
        try:
            network = MapParser(self._args.map).parse()
            finder = PathFinder(network)
            paths = finder.disjoint_paths()
            counts = finder.distribute(paths, network.nb_drones)
            if self._args.paths:
                self._show_paths(finder, paths, counts)
            simulator = Simulator(network, finder.plan())
            simulator.run()
            print(simulator.report())
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

    @staticmethod
    def _show_paths(
        finder: PathFinder,
        paths: list[Path],
        counts: list[int],
    ) -> None:
        """Print the planned routes and the expected turn count."""
        for path, count in zip(paths, counts):
            print(
                f"# {count} drone(s) | cost {path.cost} | "
                f"{' -> '.join(path.names)}",
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
