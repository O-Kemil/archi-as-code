"""Anomaly report, as specified in ADR-0006."""

from collections.abc import Callable
from dataclasses import dataclass
from datetime import date

import networkx as nx

from archinv.graph import applications_using, cycles, dependents_count
from archinv.loader import Inventory
from archinv.models import Application, Hosting, ITComponent


@dataclass(frozen=True)
class EndOfLife:
    """An IT component with its end-of-life date and the applications running on it."""

    component: ITComponent
    end_of_life: date
    applications: list[str]


def without_business_owner(inventory: Inventory) -> list[Application]:
    """Applications with no business owner, sorted by id (ADR-0001: an anomaly, not an error)."""
    found = [a for a in inventory.applications.values() if a.business_owner is None]
    return sorted(found, key=lambda a: a.id)


def _end_of_life(
    inventory: Inventory, graph: nx.DiGraph, keep: Callable[[date], bool]
) -> list[EndOfLife]:
    found = []
    for component in sorted(inventory.it_components.values(), key=lambda c: c.id):
        end_of_life = component.lifecycle.end_of_life if component.lifecycle else None
        if end_of_life is not None and keep(end_of_life):
            found.append(
                EndOfLife(
                    component, end_of_life, applications_using(graph, component.id)
                )
            )
    return found


def past_end_of_life(
    inventory: Inventory, graph: nx.DiGraph, reference: date
) -> list[EndOfLife]:
    """Components whose end of life is on or before the reference date."""
    return _end_of_life(inventory, graph, lambda end_of_life: end_of_life <= reference)


def end_of_life_before(
    inventory: Inventory, graph: nx.DiGraph, reference: date, deadline: date
) -> list[EndOfLife]:
    """Components whose end of life is after the reference date and on or before the deadline."""
    return _end_of_life(
        inventory, graph, lambda end_of_life: reference < end_of_life <= deadline
    )


def without_it_component(inventory: Inventory) -> list[Application]:
    """Applications with no IT component, except SaaS ones, which have none by construction."""
    found = [
        a
        for a in inventory.applications.values()
        if not a.it_components and a.hosting is not Hosting.SAAS
    ]
    return sorted(found, key=lambda a: a.id)


def most_depended_upon(graph: nx.DiGraph, limit: int = 10) -> list[tuple[str, int]]:
    """Applications ranked by direct dependents, most first then by id; zeros omitted."""
    ranked = sorted(
        dependents_count(graph).items(), key=lambda item: (-item[1], item[0])
    )
    return [(application, count) for application, count in ranked if count > 0][:limit]


def cell(value: object) -> str:
    """A table cell: a pipe would break the row, so it is escaped."""
    return str(value).replace("|", "\\|")


def table(headers: list[str], rows: list[tuple]) -> list[str]:
    """A Markdown table: header, separator, one line per row."""
    lines = ["| " + " | ".join(headers) + " |", "|" + "---|" * len(headers)]
    lines += ["| " + " | ".join(cell(value) for value in row) + " |" for row in rows]
    return lines


def section(title: str, body: list[str]) -> list[str]:
    """A level-2 heading and its body, or 'None.' when there is nothing to list."""
    return ["", f"## {title}", ""] + (body or ["None."])


def end_of_life_table(found: list[EndOfLife]) -> list[str]:
    if not found:
        return []
    rows = [
        (
            e.component.id,
            e.component.name,
            e.end_of_life.isoformat(),
            ", ".join(e.applications),
        )
        for e in found
    ]
    return table(["IT component", "Name", "End of life", "Applications using it"], rows)


def render(
    inventory: Inventory,
    graph: nx.DiGraph,
    reference: date,
    deadline: date | None = None,
    limit: int = 10,
) -> str:
    """The whole report as Markdown text (ADR-0006, decision 1). No generation time."""
    owners = without_business_owner(inventory)
    loops = cycles(graph)
    past = past_end_of_life(inventory, graph, reference)
    soon = (
        end_of_life_before(inventory, graph, reference, deadline) if deadline else None
    )
    bare = without_it_component(inventory)
    top = most_depended_upon(graph, limit)

    header = f"Reference date: {reference.isoformat()}."
    if deadline:
        header += f" Deadline: {deadline.isoformat()}."
    header += (
        f" Inventory: {len(inventory.applications)} applications,"
        f" {len(inventory.it_components)} IT components."
    )
    summary = [
        ("Applications without business owner", len(owners)),
        ("Circular dependencies", len(loops)),
        ("IT components past end of life", len(past)),
    ]
    if soon is not None:
        summary.append(
            (
                f"IT components reaching end of life before {deadline.isoformat()}",
                len(soon),
            )
        )
    summary.append(("Applications without IT component", len(bare)))

    lines = ["# Anomaly report", "", header]
    lines += section("Summary", table(["Anomaly", "Count"], summary))
    lines += section(
        "Applications without business owner",
        table(
            ["Application", "Name", "Technical owner"],
            [(a.id, a.name, a.technical_owner or "") for a in owners],
        )
        if owners
        else [],
    )
    lines += section(
        "Circular dependencies", [f"- {' -> '.join(c + (c[0],))}" for c in loops]
    )
    lines += section("IT components past end of life", end_of_life_table(past))
    if soon is not None:
        lines += section(
            f"IT components reaching end of life before {deadline.isoformat()}",
            end_of_life_table(soon),
        )
    lines += section(
        "Applications without IT component",
        table(
            ["Application", "Name", "Hosting"],
            [(a.id, a.name, a.hosting.value) for a in bare],
        )
        if bare
        else [],
    )
    lines += section(
        "Most depended-upon applications",
        table(["Application", "Direct dependents"], top) if top else [],
    )
    return "\n".join(lines) + "\n"
