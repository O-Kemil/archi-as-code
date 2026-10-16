# ADR-0005: Dependency graph model

- Status: Accepted
- Date: 2026-10-09
- Deciders: Kemil

## Context

The loader (ADR-0003) returns an `Inventory` of validated applications and IT components. The scoping note needs a dependency map, an anomaly report that lists circular dependencies and end-of-life technologies, and an Archi export. All three read the same structure: a *graph*, a set of nodes linked by edges, built from the inventory with NetworkX (scoping note, scope of v1). This ADR decides what the graph contains and what the module computes, so that the exports and the report can rely on it. The exports and the report are not part of this decision.

Facts verified on 2026-10-09:

- NetworkX 3.7 is the current release (PyPI and the GitHub repository, published 2026-09-21), requires Python 3.12 or later, and is distributed under the 3-clause BSD license (`LICENSE.txt` in the repository).
- NetworkX stores nodes and neighbours in dicts, so iteration follows insertion order on CPython. Its algorithms do not promise an order for their results: `simple_cycles` yields each cycle as a list of nodes, distinct cycles being those that are not cyclic permutations of each other, and `strongly_connected_components` yields sets.
- ADR-0001 (amendment of 2026-10-08) decided one edge per pair of applications, carrying the list of dependency types. ADR-0003 made ids unique across applications and IT components because the graph identifies nodes by id.

## Decision drivers

- D1. One structure feeds the map, the report and the Archi export.
- D2. Results are identical from one run to the next on the same inventory, so that `generated/` only changes when the inventory does.
- D3. Only what the scoping note needs: dependency map, cycles, end-of-life impact. The migration plan is out of scope.
- D4. No duplication of record data in the graph.

## Options considered

### Graph content

- A: applications only. Simplest, but the impact of an end-of-life component and the Archi export need the components too, so they would read two sources. Fails D1.
- B: one directed graph with two kinds of nodes, applications and IT components, and two kinds of edges, `depends_on` and `runs_on`. Computations that concern applications only use the application subgraph. A component has no outgoing edge, so it can never be part of a cycle.
- C: two graphs, applications and applications plus components. The second contains the first. Rejected.

### Node data

- A: copy fields (name, criticality, hosting) as node attributes. Exports read attributes without knowing the models, at the price of duplicated data; the current lifecycle phase depends on a reference date the graph does not have. Fails D4.
- B: attach the validated record itself as one attribute. No duplication; the generic NetworkX writers (GraphML, GEXF) cannot serialise it, which does not matter because the exports are written by this project.

### Cycle output

- A: elementary cycles from `simple_cycles`, put in a canonical form. Shows the direction of the arrows, which is what a reader needs to break a cycle. Johnson's algorithm enumerates every elementary cycle, whose number can explode in a dense cluster; `length_bound` exists to cap it.
- B: strongly connected components of size greater than one. Always stable and never combinatorial, but a set of ids does not show the arrows.

## Decision

1. Content, option B: a `networkx.DiGraph`. Nodes are record ids. Node attributes: `kind` (`application` or `it_component`) and `record` (the validated model). Edge attributes: `kind` (`depends_on` or `runs_on`); on `depends_on` edges, `types`, the dependency types of the pair sorted in enumeration order (`api`, `file`, `database`, `event`), and `dependencies`, the `Dependency` objects in record order. `DiGraph` rather than `MultiDiGraph` because ADR-0001 decided one edge per pair.
2. Computations of v1, on the inventory loaded by ADR-0003: build the graph; the application subgraph; direct dependents of an application (its predecessors); applications using an IT component (the component's predecessors); applications impacted by a change in cascade (`ancestors`); the number of direct dependents per application (raw in-degree on the application subgraph); the cycles between applications. Nothing else: no topological order, no migration waves, no normalised centrality.
3. Cycles, option A: each cycle is a tuple of ids rotated so that it starts with the smallest id, direction preserved; the list of cycles is sorted by length then alphabetically. The same inventory inserted in any order gives the same list, and a test checks it. Option B stays available if a data set ever produces a dense cluster.
4. Determinism: every result that is a collection is sorted by id before being returned.
5. NetworkX is added as a production dependency with this module (ADR-0002: dependencies arrive with the code that needs them).

## Notes

- 2026-10-16: `impacted_by` (dependents in cascade) is provided by the graph module but has no consumer in v1, neither the report nor a map. It is kept for the migration map planned in v1.1.

## Consequences

- Positive: the map, the report and the Archi export share one structure; the impact of an end-of-life component is one query; cycles are reported with their direction and stay stable in `generated/`.
- Positive: the graph makes a "criticality inversion" anomaly possible, an application depending synchronously on a less critical one; it is out of v1 and left to the report when it is wanted.
- Negative: one more dependency (NetworkX 3.7, BSD-3); computations on applications must filter the subgraph; enumerating elementary cycles has a theoretical limit on dense clusters.
- Negative: impact follows the declared direction of the links (ADR-0001, clarification of 2026-10-09: a link is declared by the application that triggers the exchange). The graph therefore answers "who connects to X", which serves the migration, but not fully "who is affected if X stops": an application that receives data pushed by another one does not appear as depending on it. Accepted limit in v1.
- Follow-up: the exports (Mermaid, Graphviz, Archi) and the report take the graph as input; grouping or filtering the map at 60 applications is an open question that may need a "domain" field (amendment of ADR-0001).

## Sources

Consulted on 2026-10-09.

- NetworkX, graph classes (`DiGraph`, attributes, dict-based storage and insertion order): https://networkx.org/documentation/stable/reference/classes/index.html
- NetworkX, `simple_cycles` (elementary cycles, Johnson's algorithm, `length_bound`): https://networkx.org/documentation/stable/reference/algorithms/generated/networkx.algorithms.cycles.simple_cycles.html
- NetworkX, `strongly_connected_components`: https://networkx.org/documentation/stable/reference/algorithms/generated/networkx.algorithms.components.strongly_connected_components.html
- NetworkX, `descendants` and `ancestors`: https://networkx.org/documentation/stable/reference/algorithms/generated/networkx.algorithms.dag.descendants.html
- NetworkX 3.7 release and license: https://pypi.org/project/networkx/ and https://github.com/networkx/networkx/blob/main/LICENSE.txt
