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
    applications_using,
    build_graph,
    dependents,
    dependents_count,
    impacted_by,
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
    # a depends on b twice (file declared before api) and on c; d depends on a;
    # a and b run on db.
    apps = [
        application(
            "a",
            depends_on=[("b", "file"), ("c", "api"), ("b", "api")],
            it_components=["db"],
        ),
        application("b", it_components=["db"]),
        application("c"),
        application("d", depends_on=[("a", "event")]),
    ]
    return Inventory({app.id: app for app in apps}, {"db": component("db")})


def test_one_node_per_record_with_its_kind(inventory):
    graph = build_graph(inventory)
    assert dict(graph.nodes(data="kind")) == {
        "a": APPLICATION,
        "b": APPLICATION,
        "c": APPLICATION,
        "d": APPLICATION,
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
    # a->b, a->c, d->a (depends_on) and a->db, b->db (runs_on)
    assert build_graph(inventory).number_of_edges() == 5


def test_empty_inventory_gives_an_empty_graph():
    graph = build_graph(Inventory({}, {}))
    assert graph.number_of_nodes() == 0


def test_application_graph_keeps_applications_and_depends_on_only(inventory):
    view = application_graph(build_graph(inventory))
    assert sorted(view.nodes) == ["a", "b", "c", "d"]
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


# Step 2: queries and dependents count (ADR-0005, decision 2).


def test_dependents_are_the_direct_predecessors(inventory):
    graph = build_graph(inventory)
    assert dependents(graph, "b") == ["a"]
    assert dependents(graph, "a") == ["d"]
    assert dependents(graph, "d") == []


def test_applications_using_a_component(inventory):
    assert applications_using(build_graph(inventory), "db") == ["a", "b"]


def test_impacted_by_follows_the_cascade(inventory):
    graph = build_graph(inventory)
    assert impacted_by(graph, "b") == ["a", "d"]
    assert impacted_by(graph, "d") == []


def test_impacted_by_a_component_includes_the_cascade(inventory):
    assert impacted_by(build_graph(inventory), "db") == ["a", "b", "d"]


def test_impacted_by_excludes_the_node_itself_inside_a_cycle():
    apps = [
        application("x", depends_on=[("y", "api")]),
        application("y", depends_on=[("x", "api")]),
    ]
    graph = build_graph(Inventory({app.id: app for app in apps}, {}))
    assert impacted_by(graph, "x") == ["y"]


def test_dependents_count_per_application_in_id_order(inventory):
    assert dependents_count(build_graph(inventory)) == {"a": 1, "b": 1, "c": 1, "d": 0}


def test_dependents_count_ignores_components(inventory):
    assert "db" not in dependents_count(build_graph(inventory))


@pytest.mark.parametrize("query", [dependents, applications_using, impacted_by])
def test_unknown_node_raises(inventory, query):
    with pytest.raises(nx.NetworkXError, match="not in the digraph"):
        query(build_graph(inventory), "nope")


def test_real_inventory_queries():
    graph = build_graph(load_inventory(INVENTORY))
    assert dependents(graph, "erp-finance") == [
        "data-warehouse",
        "hr-payroll",
        "pos-stores",
        "product-catalog",
        "supplier-portal",
        "warehouse-management",
    ]
    assert applications_using(graph, "postgresql-15") == [
        "ecommerce-site",
        "order-management",
        "supplier-portal",
    ]
    assert "bi-reporting" in impacted_by(graph, "store-inventory")
