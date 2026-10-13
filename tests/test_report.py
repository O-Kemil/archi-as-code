"""Tests for the anomaly report (ADR-0006). Acceptance list: CLAUDE.md, expected anomalies."""

from datetime import date
from pathlib import Path

import pytest

from archinv.graph import build_graph, cycles
from archinv.loader import Inventory, load_inventory
from archinv.report import (
    end_of_life_before,
    most_depended_upon,
    past_end_of_life,
    without_business_owner,
    without_it_component,
)

INVENTORY = Path(__file__).parent.parent / "inventory"
REFERENCE = date(2026, 10, 13)
DEADLINE = date(2028, 3, 31)


@pytest.fixture(scope="module")
def real():
    inventory = load_inventory(INVENTORY)
    return inventory, build_graph(inventory)


# Acceptance: the expected anomalies of the curated data set.


def test_two_applications_have_no_business_owner(real):
    inventory, _ = real
    assert [a.id for a in without_business_owner(inventory)] == [
        "bi-reporting",
        "price-label-printing",
    ]


def test_one_cycle(real):
    _, graph = real
    assert cycles(graph) == [
        ("order-management", "store-inventory", "warehouse-management")
    ]


def test_five_components_are_past_end_of_life(real):
    inventory, graph = real
    found = past_end_of_life(inventory, graph, REFERENCE)
    assert [e.component.id for e in found] == [
        "oracle-database-11g",
        "postgresql-12",
        "red-hat-enterprise-linux-7",
        "sql-server-2014",
        "windows-server-2012-r2",
    ]
    assert found[-1].applications == ["pos-stores", "price-label-printing"]


def test_two_components_reach_end_of_life_before_the_deadline(real):
    inventory, graph = real
    found = end_of_life_before(inventory, graph, REFERENCE, DEADLINE)
    assert [(e.component.id, e.end_of_life) for e in found] == [
        ("postgresql-15", date(2027, 11, 11)),
        ("windows-server-2016", date(2027, 1, 12)),
    ]


def test_no_application_without_component_outside_saas(real):
    inventory, _ = real
    assert without_it_component(inventory) == []


def test_most_depended_upon_starts_with_the_two_hubs(real):
    _, graph = real
    assert most_depended_upon(graph)[:3] == [
        ("erp-finance", 6),
        ("product-catalog", 6),
        ("loyalty-crm", 4),
    ]


# Rules, on small in-memory inventories.


def test_results_are_sorted_by_id_whatever_the_insertion_order(make_application):
    apps = {a.id: a for a in [make_application("z"), make_application("y")]}
    assert [a.id for a in without_business_owner(Inventory(apps, {}))] == ["y", "z"]


def test_end_of_life_on_the_reference_date_is_past(make_application, make_component):
    inventory = Inventory(
        {"x": make_application("x", it_components=["c"])},
        {"c": make_component("c", end_of_life="2026-10-13")},
    )
    graph = build_graph(inventory)
    found = past_end_of_life(inventory, graph, REFERENCE)
    assert [(e.component.id, e.applications) for e in found] == [("c", ["x"])]
    assert end_of_life_before(inventory, graph, REFERENCE, DEADLINE) == []


def test_end_of_life_on_the_deadline_is_before_the_deadline(make_component):
    inventory = Inventory({}, {"c": make_component("c", end_of_life="2028-03-31")})
    graph = build_graph(inventory)
    found = end_of_life_before(inventory, graph, REFERENCE, DEADLINE)
    assert [e.component.id for e in found] == ["c"]
    assert past_end_of_life(inventory, graph, REFERENCE) == []


@pytest.mark.parametrize("lifecycle", [None, {}, {"active": "2020-01-01"}])
def test_component_without_end_of_life_is_ignored(make_component, lifecycle):
    inventory = Inventory({}, {"c": make_component("c", lifecycle=lifecycle)})
    graph = build_graph(inventory)
    assert past_end_of_life(inventory, graph, REFERENCE) == []
    assert end_of_life_before(inventory, graph, REFERENCE, DEADLINE) == []


def test_saas_applications_are_not_reported_without_component(make_application):
    apps = {
        a.id: a
        for a in [
            make_application("s", hosting="saas"),
            make_application("c", hosting="cloud"),
        ]
    }
    assert [a.id for a in without_it_component(Inventory(apps, {}))] == ["c"]


def test_most_depended_upon_omits_zeros_ranks_by_count_then_id_and_cuts_at_limit(
    make_application,
):
    apps = {
        a.id: a
        for a in [
            make_application(
                "a", depends_on=[("b", "api"), ("c", "api"), ("d", "api")]
            ),
            make_application("b", depends_on=[("c", "api"), ("d", "api")]),
            make_application("c"),
            make_application("d"),
            make_application("e"),
        ]
    }
    graph = build_graph(Inventory(apps, {}))
    assert most_depended_upon(graph) == [("c", 2), ("d", 2), ("b", 1)]
    assert most_depended_upon(graph, limit=2) == [("c", 2), ("d", 2)]
