"""Tests for the map views (ADR-0007, step 1: format-independent preparation)."""

from datetime import date
from pathlib import Path

import pytest

from archinv.graph import APPLICATION, IT_COMPONENT, build_graph
from archinv.loader import Inventory, load_inventory
from archinv.maps import (
    Edge,
    Fill,
    end_of_life_view,
    focus_view,
    global_view,
    hosting_view,
)

INVENTORY = Path(__file__).parent.parent / "inventory"
REFERENCE = date(2026, 10, 14)
DEADLINE = date(2028, 3, 31)


@pytest.fixture(scope="module")
def real():
    inventory = load_inventory(INVENTORY)
    return inventory, build_graph(inventory)


def nodes_by_id(view):
    return {node.id: node for node in view.nodes}


# Curated data set.


def test_global_view_has_every_application_and_pair(real):
    view = global_view(*real, REFERENCE, DEADLINE)
    assert view.name == "global"
    assert len(view.nodes) == 15
    assert {n.kind for n in view.nodes} == {APPLICATION}
    assert len(view.edges) == 27
    assert view.groups == []
    assert Edge("supplier-portal", "erp-finance", "api, file") in view.edges


def test_global_view_labels_are_the_record_names(real):
    assert (
        nodes_by_id(global_view(*real, REFERENCE))["pos-stores"].label
        == "Point of sale"
    )


def test_signals_on_the_curated_data_set(real):
    nodes = nodes_by_id(global_view(*real, REFERENCE, DEADLINE))
    assert nodes["pos-stores"].fill is Fill.PAST_END_OF_LIFE
    assert nodes["bi-reporting"].no_owner
    assert nodes["bi-reporting"].fill is Fill.END_OF_LIFE_BEFORE_DEADLINE
    assert nodes["erp-finance"].fill is None
    assert not nodes["erp-finance"].no_owner


def test_red_wins_over_orange(real):
    # data-warehouse runs on SQL Server 2014 (past) and Windows Server 2016 (before the deadline).
    nodes = nodes_by_id(global_view(*real, REFERENCE, DEADLINE))
    assert nodes["data-warehouse"].fill is Fill.PAST_END_OF_LIFE


def test_orange_needs_a_deadline(real):
    with_deadline = nodes_by_id(global_view(*real, REFERENCE, DEADLINE))
    without = nodes_by_id(global_view(*real, REFERENCE))
    assert with_deadline["ecommerce-site"].fill is Fill.END_OF_LIFE_BEFORE_DEADLINE
    assert without["ecommerce-site"].fill is None


def test_hosting_view_groups_in_enumeration_order(real):
    view = hosting_view(*real, REFERENCE)
    assert view.name == "hosting"
    assert view.groups == ["data_center", "cloud", "saas", "store"]
    assert nodes_by_id(view)["pos-stores"].group == "store"
    assert view.edges == global_view(*real, REFERENCE).edges


def test_focus_view_is_the_induced_neighbourhood(real):
    view = focus_view(*real, "store-inventory", REFERENCE)
    assert [n.id for n in view.nodes] == [
        "order-management",
        "pos-stores",
        "product-catalog",
        "store-inventory",
        "warehouse-management",
    ]
    assert [n.id for n in view.nodes if n.emphasis] == ["store-inventory"]
    # The cycle closes between two neighbours: the induced subgraph keeps that edge.
    assert Edge("warehouse-management", "order-management", "api") in view.edges


@pytest.mark.parametrize("focus", ["nope", "postgresql-15"])
def test_focus_view_rejects_anything_but_an_application(real, focus):
    with pytest.raises(ValueError, match=f"unknown application '{focus}'"):
        focus_view(*real, focus, REFERENCE)


def test_end_of_life_view_on_the_curated_data_set(real):
    view = end_of_life_view(*real, REFERENCE, DEADLINE)
    components = [n for n in view.nodes if n.kind == IT_COMPONENT]
    assert [n.id for n in components] == [
        "oracle-database-11g",
        "postgresql-12",
        "postgresql-15",
        "red-hat-enterprise-linux-7",
        "sql-server-2014",
        "windows-server-2012-r2",
        "windows-server-2016",
    ]
    assert nodes_by_id(view)["postgresql-15"].fill is Fill.END_OF_LIFE_BEFORE_DEADLINE
    assert len([n for n in view.nodes if n.kind == APPLICATION]) == 9
    assert Edge("pos-stores", "windows-server-2012-r2") in view.edges
    assert all(e.label == "" for e in view.edges)


def test_end_of_life_view_without_deadline_keeps_the_past_only(real):
    view = end_of_life_view(*real, REFERENCE)
    assert len([n for n in view.nodes if n.kind == IT_COMPONENT]) == 5


# Rules, on in-memory inventories.


def test_nodes_and_edges_are_sorted_whatever_the_insertion_order(make_application):
    apps = [
        make_application("z", depends_on=[("y", "api")]),
        make_application("y", depends_on=[("x", "api")]),
        make_application("x"),
    ]
    inventory = Inventory({a.id: a for a in apps}, {})
    view = global_view(inventory, build_graph(inventory), REFERENCE)
    assert [n.id for n in view.nodes] == ["x", "y", "z"]
    assert view.edges == [Edge("y", "x", "api"), Edge("z", "y", "api")]


def test_hosting_groups_are_only_the_present_values(make_application):
    apps = [
        make_application("a", hosting="saas"),
        make_application("b", hosting="data_center"),
    ]
    inventory = Inventory({a.id: a for a in apps}, {})
    view = hosting_view(inventory, build_graph(inventory), REFERENCE)
    assert view.groups == ["data_center", "saas"]


def test_no_owner_flag(make_application):
    apps = [make_application("a", business_owner=None), make_application("b")]
    inventory = Inventory({a.id: a for a in apps}, {})
    nodes = nodes_by_id(global_view(inventory, build_graph(inventory), REFERENCE))
    assert nodes["a"].no_owner
    assert not nodes["b"].no_owner


def test_fill_is_none_without_end_of_life(make_application, make_component):
    inventory = Inventory(
        {"a": make_application("a", it_components=["c"])}, {"c": make_component("c")}
    )
    nodes = nodes_by_id(
        global_view(inventory, build_graph(inventory), REFERENCE, DEADLINE)
    )
    assert nodes["a"].fill is None


def test_red_wins_over_orange_in_memory(make_application, make_component):
    inventory = Inventory(
        {"a": make_application("a", it_components=["old", "soon"])},
        {
            "old": make_component("old", end_of_life="2020-01-01"),
            "soon": make_component("soon", end_of_life="2027-01-01"),
        },
    )
    nodes = nodes_by_id(
        global_view(inventory, build_graph(inventory), REFERENCE, DEADLINE)
    )
    assert nodes["a"].fill is Fill.PAST_END_OF_LIFE


def test_focus_view_includes_edges_between_neighbours(make_application):
    apps = [
        make_application("f", depends_on=[("a", "api"), ("b", "api")]),
        make_application("a", depends_on=[("b", "file")]),
        make_application("b"),
    ]
    inventory = Inventory({a.id: a for a in apps}, {})
    view = focus_view(inventory, build_graph(inventory), "f", REFERENCE)
    assert Edge("a", "b", "file") in view.edges


def test_end_of_life_view_is_empty_when_nothing_is_end_of_life(
    make_application, make_component
):
    inventory = Inventory(
        {"a": make_application("a", it_components=["c"])},
        {"c": make_component("c", end_of_life="2030-01-01")},
    )
    view = end_of_life_view(inventory, build_graph(inventory), REFERENCE)
    assert view.nodes == []
    assert view.edges == []
