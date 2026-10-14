"""Maps of the inventory, as specified in ADR-0007. Step 1: the views, independent of the format."""

from dataclasses import dataclass, field
from datetime import date
from enum import StrEnum

import networkx as nx

from archinv.graph import APPLICATION, DEPENDS_ON, IT_COMPONENT, application_graph
from archinv.loader import Inventory
from archinv.models import Application, Hosting
from archinv.report import end_of_life_before, past_end_of_life


class Fill(StrEnum):
    """The fill colour of a node (ADR-0007, decision 3)."""

    PAST_END_OF_LIFE = "past_end_of_life"  # red
    END_OF_LIFE_BEFORE_DEADLINE = "end_of_life_before_deadline"  # orange


@dataclass(frozen=True)
class Node:
    id: str
    label: str
    kind: str  # APPLICATION or IT_COMPONENT
    group: str | None = None  # hosting value in the hosting view
    no_owner: bool = False  # dashed border
    fill: Fill | None = None
    emphasis: bool = False  # the focused application


@dataclass(frozen=True)
class Edge:
    source: str
    target: str
    label: str = ""  # dependency types "api, file"; empty for runs_on


@dataclass(frozen=True)
class View:
    name: str
    nodes: list[Node]  # sorted by id (applications first in the end-of-life view)
    edges: list[Edge]  # sorted by (source, target)
    groups: list[str] = field(
        default_factory=list
    )  # hosting values present, enumeration order


GROUP_LABELS = {
    Hosting.DATA_CENTER: "Data center",
    Hosting.CLOUD: "Cloud",
    Hosting.SAAS: "SaaS",
    Hosting.STORE: "Store",
}


def fills(
    inventory: Inventory, graph: nx.DiGraph, reference: date, deadline: date | None
) -> dict[str, Fill]:
    """Fill per node id, applications and components; red wins over orange."""
    result: dict[str, Fill] = {}
    if deadline:
        for found in end_of_life_before(inventory, graph, reference, deadline):
            result[found.component.id] = Fill.END_OF_LIFE_BEFORE_DEADLINE
            for application in found.applications:
                result[application] = Fill.END_OF_LIFE_BEFORE_DEADLINE
    for found in past_end_of_life(inventory, graph, reference):
        result[found.component.id] = Fill.PAST_END_OF_LIFE
        for application in found.applications:
            result[application] = Fill.PAST_END_OF_LIFE
    return result


def application_node(
    application: Application,
    fill: dict[str, Fill],
    group: str | None = None,
    emphasis: bool = False,
) -> Node:
    return Node(
        application.id,
        application.name,
        APPLICATION,
        group,
        application.business_owner is None,
        fill.get(application.id),
        emphasis,
    )


def depends_on_edges(graph: nx.DiGraph, node_ids: set[str]) -> list[Edge]:
    """The depends_on edges between the given nodes, labelled with the types, sorted."""
    edges = [
        Edge(source, target, ", ".join(t.value for t in data["types"]))
        for source, target, data in graph.edges(data=True)
        if data["kind"] == DEPENDS_ON and source in node_ids and target in node_ids
    ]
    return sorted(edges, key=lambda e: (e.source, e.target))


def global_view(
    inventory: Inventory,
    graph: nx.DiGraph,
    reference: date,
    deadline: date | None = None,
    grouped: bool = False,
) -> View:
    """Every application and every pair; grouped by hosting when asked (the hosting view)."""
    fill = fills(inventory, graph, reference, deadline)
    applications = sorted(inventory.applications.values(), key=lambda a: a.id)
    nodes = [
        application_node(a, fill, a.hosting.value if grouped else None)
        for a in applications
    ]
    groups = []
    if grouped:
        groups = [h.value for h in Hosting if any(a.hosting is h for a in applications)]
    ids = {a.id for a in applications}
    return View(
        "hosting" if grouped else "global", nodes, depends_on_edges(graph, ids), groups
    )


def hosting_view(
    inventory: Inventory,
    graph: nx.DiGraph,
    reference: date,
    deadline: date | None = None,
) -> View:
    return global_view(inventory, graph, reference, deadline, grouped=True)


def focus_view(
    inventory: Inventory,
    graph: nx.DiGraph,
    focus: str,
    reference: date,
    deadline: date | None = None,
) -> View:
    """One application, its direct dependents and dependencies, and every edge between them."""
    if focus not in inventory.applications:
        raise ValueError(f"unknown application '{focus}'")
    applications = application_graph(graph)
    ids = {focus, *applications.predecessors(focus), *applications.successors(focus)}
    fill = fills(inventory, graph, reference, deadline)
    nodes = [
        application_node(inventory.applications[i], fill, emphasis=(i == focus))
        for i in sorted(ids)
    ]
    return View("focus", nodes, depends_on_edges(graph, ids))


def end_of_life_view(
    inventory: Inventory,
    graph: nx.DiGraph,
    reference: date,
    deadline: date | None = None,
) -> View:
    """The components past end of life (or before the deadline) and the applications using them.

    Applications come first, then components, each group sorted by id, so that a renderer
    can draw the two kinds apart without sorting again (ADR-0007, decision 4).
    """
    fill = fills(inventory, graph, reference, deadline)
    components = sorted(c for c in inventory.it_components if c in fill)
    applications = sorted({a for c in components for a in graph.predecessors(c)})
    nodes = [application_node(inventory.applications[a], fill) for a in applications]
    nodes += [
        Node(c, inventory.it_components[c].name, IT_COMPONENT, fill=fill[c])
        for c in components
    ]
    edges = sorted(
        (Edge(a, c) for c in components for a in graph.predecessors(c)),
        key=lambda e: (e.source, e.target),
    )
    return View("end-of-life", nodes, edges)


# Mermaid rendering (ADR-0007, decision 1). One documented "style" statement per decorated node:
# the documentation does not promise that several "class" statements on one node accumulate.

MERMAID_FILL = {
    Fill.PAST_END_OF_LIFE: "fill:#f8d0d0,stroke:#b03030",
    Fill.END_OF_LIFE_BEFORE_DEADLINE: "fill:#fde4c0,stroke:#c07020",
}
MERMAID_NO_OWNER = "stroke-dasharray: 6 4"
MERMAID_EMPHASIS = "stroke-width:3px"


def mermaid_id(record_id: str) -> str:
    """Hyphens have a meaning in Mermaid; slugs never contain underscores, so no collision."""
    return record_id.replace("-", "_")


def mermaid_label(text: str) -> str:
    """Labels are quoted; a quote inside becomes the Mermaid entity code."""
    return text.replace('"', "#quot;")


def mermaid_node(node: Node) -> str:
    label = mermaid_label(node.label)
    shape = f'[("{label}")]' if node.kind == IT_COMPONENT else f'["{label}"]'
    return f"{mermaid_id(node.id)}{shape}"


def mermaid_style(node: Node) -> str:
    """The style of a node from its signals, in a fixed order: fill, border, emphasis."""
    parts = []
    if node.fill:
        parts.append(MERMAID_FILL[node.fill])
    if node.no_owner:
        parts.append(MERMAID_NO_OWNER)
    if node.emphasis:
        parts.append(MERMAID_EMPHASIS)
    return ",".join(parts)


def to_mermaid(view: View) -> str:
    """A flowchart, left to right, with the conventions of ADR-0007 as node styles."""
    lines = ["flowchart LR"]
    if view.groups:
        for group in view.groups:
            lines.append(f'    subgraph {group}["{GROUP_LABELS[Hosting(group)]}"]')
            lines += [
                f"        {mermaid_node(n)}" for n in view.nodes if n.group == group
            ]
            lines.append("    end")
    else:
        lines += [f"    {mermaid_node(n)}" for n in view.nodes]
    for edge in view.edges:
        arrow = f"-->|{mermaid_label(edge.label)}|" if edge.label else "-->"
        lines.append(f"    {mermaid_id(edge.source)} {arrow} {mermaid_id(edge.target)}")
    for node in view.nodes:
        if style := mermaid_style(node):
            lines.append(f"    style {mermaid_id(node.id)} {style}")
    return "\n".join(lines) + "\n"
