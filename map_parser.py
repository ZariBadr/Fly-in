"""Parsing and validation of Fly-in map files."""

from __future__ import annotations

from typing import NoReturn

from models import Connection, Network, Zone, ZoneType

ZONE_KEYWORDS = ("start_hub", "end_hub", "hub")
ZONE_META = ("zone", "color", "max_drones")
LINK_META = ("max_link_capacity",)
BAD_NAME_CHARS = "-[]#:"


class ParseError(Exception):
    """A syntax or consistency error located in a map file."""

    def __init__(self, line: int, reason: str, content: str = "") -> None:
        """Store the location and cause, and build the message."""
        self.line_number = line
        self.reason = reason
        where = f" at line {line}" if line else ""
        echo = f"\n    >>> {content}" if content else ""
        super().__init__(f"parse error{where}: {reason}{echo}")


class MapParser:
    """Read a map file and produce a validated Network."""

    def __init__(self, path: str) -> None:
        """Bind the parser to a map file path."""
        self._path = path
        self._net: Network | None = None
        self._links: set[frozenset[str]] = set()
        self._line = 0
        self._raw = ""

    def parse(self) -> Network:
        """Parse the file and return the validated network."""
        self._net, self._links = None, set()
        try:
            with open(self._path, encoding="utf-8-sig") as handle:
                lines = handle.readlines()
        except OSError as error:
            raise ParseError(0, f"cannot read '{self._path}': {error}")
        for self._line, raw in enumerate(lines, start=1):
            self._raw = raw.split("#", 1)[0].strip()
            if self._raw:
                self._dispatch()
        return self._finalise()

    def _fail(self, reason: str) -> NoReturn:
        """Raise a ParseError pointing at the line being parsed."""
        raise ParseError(self._line, reason, self._raw)

    def _dispatch(self) -> None:
        """Route the current line to the handler for its keyword."""
        if ":" not in self._raw:
            self._fail("missing ':' separator after the keyword")
        keyword, _, rest = self._raw.partition(":")
        keyword, rest = keyword.strip(), rest.strip()
        if keyword == "nb_drones":
            self._parse_nb_drones(rest)
        elif self._net is None:
            self._fail("the first instruction must be 'nb_drones: <number>'")
        elif keyword in ZONE_KEYWORDS:
            self._parse_zone(keyword, rest)
        elif keyword == "connection":
            self._parse_connection(rest)
        else:
            self._fail(f"unknown keyword '{keyword}'")

    def _parse_nb_drones(self, rest: str) -> None:
        """Handle 'nb_drones: <n>', which creates the network."""
        if self._net is not None:
            self._fail("nb_drones is declared twice")
        self._net = Network(self._number(rest, "nb_drones"))

    def _parse_zone(self, keyword: str, rest: str) -> None:
        """Handle a 'hub:', 'start_hub:' or 'end_hub:' line."""
        net = self._require_net()
        body, meta = self._meta(rest, ZONE_META)
        fields = body.split()
        if len(fields) != 3:
            self._fail("expected '<name> <x> <y>' before the metadata")
        name, raw_x, raw_y = fields
        for char in BAD_NAME_CHARS:
            if char in name:
                self._fail(
                    f"zone name '{name}' contains a forbidden "
                    f"character '{char}'"
                )
        if net.has_zone(name):
            self._fail(f"duplicate zone name '{name}'")
        is_start, is_end = keyword == "start_hub", keyword == "end_hub"
        if is_start and net.has_start:
            self._fail("a second start_hub is defined")
        if is_end and net.has_end:
            self._fail("a second end_hub is defined")
        net.add_zone(Zone(
            name,
            self._number(raw_x, "x coordinate", positive=False),
            self._number(raw_y, "y coordinate", positive=False),
            self._zone_type(meta.get("zone")),
            meta.get("color"),
            self._number(meta.get("max_drones", "1"), "max_drones"),
            is_start,
            is_end,
        ))

    def _parse_connection(self, rest: str) -> None:
        """Handle a 'connection: <zone1>-<zone2>' line."""
        net = self._require_net()
        body, meta = self._meta(rest, LINK_META)
        if not body or " " in body:
            self._fail("expected '<zone1>-<zone2>' without spaces")
        ends = body.split("-")
        if len(ends) != 2 or not all(ends):
            self._fail(
                "a connection links exactly two zones separated by one "
                "dash (dashes are forbidden inside zone names)"
            )
        first, second = ends
        if first == second:
            self._fail(f"'{first}' cannot be connected to itself")
        for name in ends:
            if not net.has_zone(name):
                self._fail(f"connection refers to undefined zone '{name}'")
        if frozenset(ends) in self._links:
            self._fail(
                f"duplicate connection between '{first}' and '{second}'"
            )
        self._links.add(frozenset(ends))
        net.add_connection(Connection(
            first,
            second,
            self._number(
                meta.get("max_link_capacity", "1"), "max_link_capacity"
            ),
        ))

    def _meta(
        self,
        text: str,
        allowed: tuple[str, ...],
    ) -> tuple[str, dict[str, str]]:
        """Split 'body [k=v ...]' into its body and its metadata."""
        head, bracket, tail = text.partition("[")
        if not bracket:
            if "]" in text:
                self._fail("closing ']' without an opening '['")
            return text.strip(), {}
        tail = tail.strip()
        if not tail.endswith("]"):
            self._fail("unclosed metadata block")
        body = tail[:-1]
        if "[" in body or "]" in body:
            self._fail("nested or malformed metadata block")
        meta: dict[str, str] = {}
        for token in body.split():
            key, sep, value = token.partition("=")
            if not (sep and key and value) or "=" in value:
                self._fail(
                    f"malformed metadata entry '{token}' (expected key=value)"
                )
            if key in meta:
                self._fail(f"metadata key '{key}' is repeated")
            if key not in allowed:
                self._fail(
                    f"unknown metadata key '{key}' "
                    f"(allowed here: {', '.join(allowed)})"
                )
            meta[key] = value
        return head.strip(), meta

    def _zone_type(self, raw: str | None) -> ZoneType:
        """Return the declared zone type, defaulting to normal."""
        if raw is None:
            return ZoneType.NORMAL
        try:
            return ZoneType.from_string(raw)
        except ValueError as error:
            self._fail(str(error))

    def _number(self, raw: str, label: str, positive: bool = True) -> int:
        """Convert raw to an int, optionally requiring it to be positive."""
        try:
            value = int(raw)
        except ValueError:
            self._fail(f"{label} must be an integer, got '{raw}'")
        if positive and value <= 0:
            self._fail(f"{label} must be a positive integer, got {value}")
        return value

    def _require_net(self) -> Network:
        """Return the network under construction."""
        if self._net is None:
            self._fail("nb_drones must be declared first")
        return self._net

    def _finalise(self) -> Network:
        """Run the end-of-file checks and return the network."""
        self._line, self._raw = 0, ""
        net = self._require_net()
        if not net.has_start:
            self._fail("no 'start_hub' zone was defined")
        if not net.has_end:
            self._fail("no 'end_hub' zone was defined")
        if net.start.name == net.end.name:
            self._fail("start and end hubs must be distinct")
        return net
