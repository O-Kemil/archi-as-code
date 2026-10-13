"""Anomaly report, as specified in ADR-0006."""

from collections.abc import Callable
from dataclasses import dataclass
from datetime import date

import networkx as nx

from archinv.graph import applications_using, dependents_count
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
