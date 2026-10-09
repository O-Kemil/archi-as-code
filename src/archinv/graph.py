"""Dependency graph, as specified in ADR-0005."""

import networkx as nx

from archinv.loader import Inventory
from archinv.models import DependencyType

APPLICATION = "application"
IT_COMPONENT = "it_component"
DEPENDS_ON = "depends_on"
RUNS_ON = "runs_on"

# Position of each dependency type in the enumeration, to sort edge types stably.
TYPE_ORDER = {kind: index for index, kind in enumerate(DependencyType)}


def build_graph(inventory: Inventory) -> nx.DiGraph:
    """One node per record, one depends_on edge per pair, one runs_on edge per component.

    The inventory is already validated (ADR-0003), so every target exists.
    """
    graph = nx.DiGraph()
    for application in inventory.applications.values():
        graph.add_node(application.id, kind=APPLICATION, record=application)
    for component in inventory.it_components.values():
        graph.add_node(component.id, kind=IT_COMPONENT, record=component)
    for application in inventory.applications.values():
        by_target: dict[str, list] = {}
        for dependency in application.depends_on:
            by_target.setdefault(dependency.application, []).append(dependency)
        for target, dependencies in by_target.items():
            types = sorted({d.type for d in dependencies}, key=TYPE_ORDER.__getitem__)
            graph.add_edge(
                application.id,
                target,
                kind=DEPENDS_ON,
                types=types,
                dependencies=dependencies,
            )
        for component in application.it_components:
            graph.add_edge(application.id, component, kind=RUNS_ON)
    return graph


def application_graph(graph: nx.DiGraph) -> nx.DiGraph:
    """Read-only view with the application nodes and, therefore, the depends_on edges only."""
    applications = [
        node for node, kind in graph.nodes(data="kind") if kind == APPLICATION
    ]
    return graph.subgraph(applications)
