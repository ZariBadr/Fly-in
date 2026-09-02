*This project has been created as part
of the 42 curriculum by bzari*

## Description

**Fly-in** is a drone fleet routing simulator. Given a text file describing a network of
connected zones, it moves every drone from the **start hub** to the **end hub** in the
**fewest possible simulation turns**, while respecting the movement, occupancy and
zone-type rules defined by the map.

### Goal

The program reads a map, builds the corresponding graph, computes a routing plan for the
whole fleet, and replays it turn by turn. Performance is measured by the **total number of
simulation turns** needed to deliver all drones: the fewer, the better. The real challenge
is not finding *a* path, but scheduling *many* drones at once over a congested graph —
splitting the fleet across several routes, making some drones wait on purpose, and avoiding
collisions and deadlocks.

### Rules of the world

Each zone has a type that drives its cost and accessibility:

| Type | Behaviour |
| --- | --- |
| `normal` | Costs 1 turn to enter (default) |
| `priority` | Costs 1 turn, but is preferred when several routes tie |
| `restricted` | Costs 2 turns; the drone spends the intermediate turn **on the connection**, and cannot stop mid-flight |
| `blocked` | Inaccessible — any route using it is invalid |

On top of that, every zone has a maximum simultaneous occupancy (`max_drones`, default 1)
and every connection a maximum simultaneous traversal count (`max_link_capacity`,
default 1). The start and end hubs are the only exceptions: all drones share the start hub
at turn 0, and any number of drones may be delivered to the end hub.

### Overview

The project is written in Python, fully object-oriented and strictly type-annotated, with **no graph library** — every traversal is implemented by
hand. It is split into clearly separated components:

- **Parser** — strict validation of the map format, with errors reporting the exact line
  and cause.
- **Network model** — zones, connections and the graph they form.
- **Planner** — the pathfinding and scheduling engine that produces the movement plan.
- **Simulation engine** — replays the plan and independently re-checks every rule
  (adjacency, travel costs, zone and link capacities, restricted-zone timing).
- **Visualisation** — colourised terminal output showing the network and the drones moving
  through it, turn after turn.

The simulation output follows the format required by the subject: one line per turn,
listing the movements of that turn as `D<ID>-<zone>` (or `D<ID>-<connection>` while a drone
is still in flight toward a restricted zone).

```
D1-roof1 D2-corridorA
D1-roof2 D2-tunnelB
D1-goal D2-goal
```

## Instructions

### Requirements

- **Python 3.10 or later** (`python3 --version`)
- `pip` (or `uv` / `pipx`) to install the development dependencies
- No runtime dependency: the program runs on the standard library only.
  `flake8`, `mypy` and `pytest` are only needed for linting and testing.

### Installation

```bash
git clone <repository-url>
cd <repository-name>
make install
```

It is recommended to work inside a virtual environment:

```bash
python3 -m venv .venv
source .venv/bin/activate      # Windows: .venv\Scripts\activate
make install
```

### Execution

Run the simulation on a map file:

```bash
python3 main.py maps/easy_1_linear_path.txt
```

Or through the Makefile, which uses a default map:

```bash
make run                                   # default map
make run MAP=maps/hard_2_capacity_hell.txt # custom map
```

### Command line options

| Option | Effect |
| --- | --- |
| `<map file>` | Path to the map to simulate (required) |
| `-h`, `--help` | Show the full usage message |
| `--plain` | Print only the turn lines, without any decoration |
| `--no-color` | Disable ANSI colours (useful when piping to a file) |
| `--board` | Draw the network and the drone positions at every turn |
| `--delay <seconds>` | Pause between turns, to watch the simulation live |
| `--stats` | Display the performance metrics at the end |
| `--quiet` | Suppress everything except the simulation output |

Examples:

```bash
python3 main.py maps/medium_3_priority_puzzle.txt --board --delay 0.4
python3 main.py maps/hard_3_ultimate_challenge.txt --stats
python3 main.py maps/easy_2_simple_fork.txt --plain > result.txt
```

The decorative output (header, board, metrics) is written to **stderr**, while the
protocol lines are written to **stdout**. Redirecting stdout therefore always gives a
file containing strictly the required format:

## Resources

### Graph theory and pathfinding

- [Dijkstra's algorithm — Wikipedia](https://en.wikipedia.org/wiki/Dijkstra%27s_algorithm)
- [Breadth-first search — Wikipedia](https://en.wikipedia.org/wiki/Breadth-first_search)

### Terminal rendering

- [ANSI escape codes — Wikipedia](https://en.wikipedia.org/wiki/ANSI_escape_code)
- [Bresenham's line algorithm — Wikipedia](https://en.wikipedia.org/wiki/Bresenham%27s_line_algorithm)
  (used to draw the connections on the terminal map)

---

## Use of AI

AI (Claude) was used as a *research and review assistant*, not as a code generator whose
output was pasted blindly. Every piece of code in this repository was read, understood,
tested and reworked; I am able to explain and modify any part of it during the evaluation.

**Where AI was used:**

- **Understanding the problem.** Rephrasing the subject's constraints (restricted zones
  costing 2 turns with a mandatory arrival, zone vs. link capacities, start/end
  exceptions) and checking that my reading of the rules was consistent.
- **Algorithm exploration.** Comparing candidate strategies — greedy BFS with a
  reservation table, disjoint-path decomposition à la `lem-in`, and a time-expanded flow
  model — and discussing the trade-offs of each before I chose the final approach. The
  limits of the flow model (how link capacity behaves during a 2-turn crossing) were
  identified during that discussion and are documented in the technical choices section.
- **Boilerplate and refactoring.** Suggestions on splitting the code into modules,
  writing PEP 257 docstrings, and fixing `mypy --strict` and `flake8` complaints.
- **Test map design.** Brainstorming edge cases to cover (dead ends, cycles, blocked
  zones, bottlenecks, invalid syntax) which I then turned into the files in `maps/` and
  `maps/errors/`.
- **README wording.** Structuring and proof-reading this document.

**Where AI was *not* used:**

- The final choice of algorithm and the data structures behind it.
- The validation logic of the simulation engine, which I wrote to double-check the
  planner's output independently.
- Any acceptance of code I could not explain: every suggestion was re-implemented or
  rewritten after being understood, and reviewed with peers.


## Algorithm choices and implementation strategy

### The problem in one sentence

Moving one drone is a shortest-path problem; moving a whole fleet is a **scheduling**
problem. Once several drones share a graph whose zones hold one drone at a time, the
optimal answer is rarely "send everyone down the shortest path" — it is a trade-off
between path length, path count and congestion. The metric to minimise is the number of
turns until the **last** drone lands, not the average trip length.

### Options considered

1. **Greedy BFS + reservation table.** Each drone reserves `(zone, turn)` cells; conflicts
   are resolved by waiting. Simple and fast, but purely local: it produces valid
   schedules, not minimal ones, and it deadlocks on maps with narrow bottlenecks.
2. **Disjoint-path decomposition (the classic `lem-in` approach).** Extract a set of
   vertex-disjoint paths, then distribute drones across them so that every path finishes
   at the same turn. Excellent on clean maps, but it does not natively express
   `max_drones > 1`, `max_link_capacity > 1`, nor the 2-turn cost of restricted zones —
   all of which this subject adds.
3. **Time-expanded flow model (chosen).** Duplicate the graph once per turn and turn the
   whole question into a single max-flow problem. Capacities, waiting, simultaneous
   movement and multi-turn crossings all become ordinary edges, and the answer is
   provably minimal for the model.

I chose option 3 because it is the only one that handles *every* constraint of the subject
uniformly, and because it gives a guarantee rather than a heuristic.

### The time-expanded network

The idea (Ford & Fulkerson's *dynamic flows*) is that "route N drones in at most T turns"
is equivalent to "push N units of flow through a static graph built from T copies of the
map". One unit of flow = one drone; the path it follows through the expanded graph *is*
its trajectory in space **and** time.

The construction, for every turn `t`:

- **Zone occupancy — node splitting.** Each zone `v` becomes two nodes `v_in(t)` and
  `v_out(t)` joined by an edge of capacity `max_drones(v)`. A drone standing in `v` at
  turn `t` must cross that edge, so the zone can never be over-occupied. The start and end
  hubs get an unlimited capacity, as the subject requires.
- **Waiting.** `v_out(t) → v_in(t+1)` with unlimited capacity: staying in place is just
  another edge, so "strategic waiting" needs no special case in the code.
- **Link capacity — slot nodes.** Each connection `c` gets a per-turn node of capacity
  `max_link_capacity(c)`, fed by both endpoints. Because the two directions share the same
  node, the capacity is shared as well.
- **Normal / priority moves.** `u_out(t) → slot(c,t) → v_in(t+1)`: one turn.
- **Restricted moves.** `u_out(t) → slot(c,t) → transit(c,v,t+1) → v_in(t+2)`. The
  `transit` node literally *is* the "drone is on the connection" state described by the
  subject: it is what gets printed as `D<ID>-<connection>`, and because it has no waiting
  edge, a drone physically **cannot** stall mid-flight — the rule is enforced by the shape
  of the graph rather than by a check.
- **Source and sink.** `SOURCE → start_in(0)` with capacity `nb_drones`; `end_in(t) → SINK`
  with unlimited capacity for every `t`, so a drone that lands is delivered and no longer
  tracked.

### Finding the minimum number of turns

Rather than binary-searching on `T`, the horizon is grown **incrementally**: layer `t` is
appended to the graph, then the max-flow is resumed on the existing residual network.
Adding a layer only ever adds capacity, so the flow already found stays valid and no work
is repeated. The loop stops at the first `t` where the flow reaches `nb_drones` — that `t`
is the optimal turn count for this model.

The max-flow itself is **Dinic's algorithm**, written from scratch (BFS level graph +
blocking flow with a per-node cursor, iterative DFS to avoid recursion limits on deep
time-expanded graphs). No graph library is used anywhere; only `heapq` for Dijkstra.

### Pruning and preferences

- **Dijkstra pre-pass.** A weighted shortest-path run (edge weight = travel cost of the
  destination zone: 1, or 2 for restricted) gives the earliest turn each zone can possibly
  be reached. Layers never create nodes for a zone before that turn, which cuts the
  expanded graph substantially. The same pass detects an unreachable end hub and fails
  early with a clear message instead of expanding forever.
- **Priority zones.** The subject asks for them to be *preferred*, not cheaper. Since many
  schedules share the same optimal turn count, the tie is broken inside the solver: edges
  leading into `priority` zones are inserted at the front of the adjacency lists, so
  Dinic's DFS explores them first and the returned optimum is the one that favours them.
- **Blocked zones** are simply never given nodes, so no path can use them by construction.

### From flow to drone routes

Once the flow saturates, it is **decomposed into unit paths**: starting at the source, one
unit of flow is followed edge by edge and consumed. The expanded graph is a DAG (time only
moves forward), so decomposition terminates and produces no cycles. Each unit path visits
exactly one "position node" per turn, giving a complete `turn → position` timeline per
drone. Routes are then sorted by arrival time and numbered `D1..DN`.

### Independent verification

The planner and the simulator are deliberately separate. The `Simulation` class replays the
plan and re-checks, without trusting the solver:

- drones start at the start hub and end at the end hub;
- every move follows an existing connection, and never enters a blocked zone;
- a restricted zone is always reached through exactly one transit turn, never in one turn
  and never with a pause on the link;
- per turn, zone occupancy ≤ `max_drones` (start/end excepted) and connection usage ≤
  `max_link_capacity`.

Any violation raises instead of printing a plausible-looking but illegal result. This is
also what makes the project safe to modify during the defence: break the planner and the
simulator says so.

### Complexity

Let `V` be the zones, `E` the connections, `T` the final turn count and `N` the drones.
The expanded graph has `O((V + E) · T)` nodes and edges. Dinic on unit-ish capacities runs
in `O(E' · √V')` in practice, and the incremental construction means the graph is built
once, not once per candidate horizon. Dijkstra costs `O((V + E) log V)`. Memory is
`O((V + E) · T)` — the honest cost of the approach, and the reason for the earliest-arrival
pruning. Nothing is recomputed between turns: the whole plan is produced once, then merely
replayed.

### Known modelling limit (discussed openly)

A flow network has no memory, so a crossing that spans two turns cannot consume the *same*
capacity node twice without also creating an illegal one-turn shortcut. The model therefore
enforces `max_link_capacity` as two separate constraints: at most `K` drones may **start**
a crossing of a connection on a given turn, and at most `K` drones may be **in flight** on
it at a given turn. In the rare configuration where a drone lands from a 2-turn crossing on
the same turn another departs, the link is momentarily used by two drones. This is a
conscious trade-off — the alternative is an exact but exponential formulation — and the
simulator applies the same rule, so the reported plan is always consistent with the
documented semantics.

---

## Visual representation

The subject requires visual feedback; the project provides a **coloured terminal
visualisation**, designed so that it never interferes with the machine-readable output.

### Separation of the two output streams

- **stdout** carries strictly the protocol lines — one line per turn, movements separated
  by spaces, `D<ID>-<zone>` or `D<ID>-<connection>`.
- **stderr** carries everything decorative: header, board, legend, metrics.

So `python3 main.py map.txt > result.txt` yields a file containing exactly the required
format, while the human still watches the pretty version on screen. `--plain` disables the
decoration entirely, `--quiet` silences stderr, and `--no-color` (or a non-TTY, or
`NO_COLOR=1`) strips the escape sequences automatically.

### Features

**1. Map header.** Before the run: number of drones, zones, connections, how many are
blocked / restricted / priority, and one cheapest route with its cost. It tells the
reviewer at a glance what kind of map they are looking at and what a "good" turn count
would be.

**2. Colour-coded zones.** Colours declared with `color=` in the map file are honoured
verbatim; any single word is accepted, unknown names being hashed into the 256-colour cube
so authors can invent colours freely. Zones without a colour fall back to a type-based
default, and each type also carries a symbol (`o` normal, `*` priority, `!` restricted,
`X` blocked) so the display remains readable in monochrome or for colour-blind users —
colour is never the only carrier of meaning.

**3. Turn-by-turn movement lines.** Each turn is numbered and its movements are printed in
the destination zone's colour, so a wave of drones moving through a corridor is visible as
a block of one colour. Drones entering a restricted link are shown flying over the
connection, which makes the 2-turn rule obvious rather than something you have to infer
from the log.

**4. The board (`--board`).** An ASCII map drawn from the zones' `x`/`y` coordinates:
connections are traced with Bresenham's line algorithm, zones are placed with their symbol,
name and current drone count. Redrawn every turn, it turns the log into an animation —
combined with `--delay`, you can literally watch the fleet spread across the network, pile
up behind a bottleneck and drain into the goal. This is where the visualisation earns its
keep: congestion, unused branches and waiting drones are immediately obvious, whereas they
are nearly invisible in a wall of text.

**5. Legend.** A compact reminder of symbols and zone types, so the board is
self-explanatory to someone who has never seen the project.

**6. Metrics (`--stats`).** Total turns, number of drones, total movements, average
movements per turn, average turns per drone, and total weighted path cost — the secondary
metrics the subject suggests for comparing two solutions with the same turn count.
