"""Tests for the dependency graph (ADR-0005)."""

from pathlib import Path

import networkx as nx
import pytest

from archinv.graph import (
    APPLICATION,
    DEPENDS_ON,
    IT_COMPONENT,
    RUNS_ON,
    application_graph,
    build_graph,
)
from archinv.loader import Inventory, load_inventory
from archinv.models import Application, DependencyType, ITComponent

INVENTORY = Path(__file__).parent.parent / "inventory"


def application(record_id, depends_on=(), it_components=()):
    return Application(
        id=record_id,
        name=record_id,
        description="d",
        business_criticality="administrative_service",
        hosting="cloud",
        lifecycle={"active": "2020-01-01"},
        depends_on=[{"application": t, "type": k} for t, k in depends_on],
        it_components=list(it_components),
    )


def component(record_id):
    return ITComponent(id=record_id, name=record_id, category="software")


@pytest.fixture
def inventory():
    # a depends on b twice (file declared before api) and on c; a and b run on db.
    apps = [
        application(
            "a",
            depends_on=[("b", "file"), ("c", "api"), ("b", "api")],
            it_components=["db"],
        ),
        application("b", it_components=["db"]),
        application("c"),
    ]
    return Inventory({app.id: app for app in apps}, {"db": component("db")})


def test_one_node_per_record_with_its_kind(inventory):
    graph = build_graph(inventory)
    assert dict(graph.nodes(data="kind")) == {
        "a": APPLICATION,
        "b": APPLICATION,
        "c": APPLICATION,
        "db": IT_COMPONENT,
    }


def test_node_record_is_the_validated_model(inventory):
    graph = build_graph(inventory)
    assert graph.nodes["a"]["record"] is inventory.applications["a"]
    assert graph.nodes["db"]["record"] is inventory.it_components["db"]


def test_one_depends_on_edge_per_pair(inventory):
    graph = build_graph(inventory)
    assert graph.has_edge("a", "b")
    assert graph.number_of_edges("a", "b") == 1
    assert graph.edges["a", "b"]["kind"] == DEPENDS_ON


def test_edge_types_are_sorted_in_enumeration_order(inventory):
    graph = build_graph(inventory)
    assert graph.edges["a", "b"]["types"] == [DependencyType.API, DependencyType.FILE]


def test_edge_keeps_the_dependencies_in_record_order(inventory):
    graph = build_graph(inventory)
    assert [d.type for d in graph.edges["a", "b"]["dependencies"]] == [
        DependencyType.FILE,
        DependencyType.API,
    ]


def test_runs_on_edge_per_component(inventory):
    graph = build_graph(inventory)
    assert graph.edges["a", "db"] == {"kind": RUNS_ON}
    assert graph.edges["b", "db"] == {"kind": RUNS_ON}


def test_edge_count(inventory):
    # a->b, a->c (depends_on) and a->db, b->db (runs_on)
    assert build_graph(inventory).number_of_edges() == 4


def test_empty_inventory_gives_an_empty_graph():
    graph = build_graph(Inventory({}, {}))
    assert graph.number_of_nodes() == 0


def test_application_graph_keeps_applications_and_depends_on_only(inventory):
    view = application_graph(build_graph(inventory))
    assert sorted(view.nodes) == ["a", "b", "c"]
    assert {kind for _, _, kind in view.edges(data="kind")} == {DEPENDS_ON}


def test_application_graph_is_a_read_only_view(inventory):
    view = application_graph(build_graph(inventory))
    with pytest.raises(nx.NetworkXError):
        view.add_node("x")


def test_the_real_inventory_builds_as_expected():
    loaded = load_inventory(INVENTORY)
    graph = build_graph(loaded)
    assert graph.number_of_nodes() == len(loaded.applications) + len(
        loaded.it_components
    )
    assert graph.edges["supplier-portal", "erp-finance"]["types"] == [
        DependencyType.API,
        DependencyType.FILE,
    ]
