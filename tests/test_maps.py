"""Tests for the maps (ADR-0007): the views and their renderings."""

from datetime import date
from pathlib import Path

import pytest

from archinv.graph import APPLICATION, IT_COMPONENT, build_graph
from archinv.loader import Inventory, load_inventory
from archinv.maps import (
    Edge,
    Fill,
    Node,
    View,
    dot_quote,
    end_of_life_view,
    focus_view,
    global_view,
    hosting_view,
    mermaid_id,
    mermaid_label,
    to_dot,
    to_mermaid,
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


# Mermaid rendering (ADR-0007, decision 1).


def test_mermaid_id_replaces_hyphens():
    assert mermaid_id("pos-stores") == "pos_stores"


def test_mermaid_label_escapes_quotes():
    assert mermaid_label('Say "hi"') == "Say #quot;hi#quot;"


def test_mermaid_of_an_empty_view_is_a_valid_empty_flowchart():
    assert to_mermaid(View("global", [], [])) == "flowchart LR\n"


def test_mermaid_application_and_component_shapes():
    view = View(
        "end-of-life",
        [Node("app-a", "App A", APPLICATION), Node("db-1", "DB 1", IT_COMPONENT)],
        [],
    )
    text = to_mermaid(view)
    assert '    app_a["App A"]' in text
    assert '    db_1[("DB 1")]' in text


def test_mermaid_edges_with_and_without_label():
    view = View(
        "x",
        [Node("a", "A", APPLICATION), Node("b", "B", APPLICATION)],
        [Edge("a", "b", "api, file"), Edge("b", "a")],
    )
    text = to_mermaid(view)
    assert "    a -->|api, file| b" in text
    assert "    b --> a" in text


def test_mermaid_groups_become_subgraphs_with_their_labels(real):
    text = to_mermaid(hosting_view(*real, REFERENCE))
    assert '    subgraph data_center["Data center"]' in text
    assert '        pos_stores["Point of sale"]' in text
    assert text.count("    end\n") == 4


def test_mermaid_styles_follow_the_signals(real):
    text = to_mermaid(hosting_view(*real, REFERENCE, DEADLINE))
    assert "    style data_warehouse fill:#f8d0d0,stroke:#b03030\n" in text
    assert (
        "    style bi_reporting fill:#fde4c0,stroke:#c07020,stroke-dasharray: 6 4\n"
        in text
    )
    assert "style erp_finance" not in text


def test_mermaid_emphasis_on_the_focus(real):
    text = to_mermaid(focus_view(*real, "store-inventory", REFERENCE))
    assert "    style store_inventory stroke-width:3px\n" in text
    assert text.count("stroke-width:3px") == 1


def test_mermaid_is_deterministic(real):
    first = to_mermaid(hosting_view(*real, REFERENCE, DEADLINE))
    second = to_mermaid(hosting_view(*real, REFERENCE, DEADLINE))
    assert first == second


def test_mermaid_of_the_curated_hosting_view_has_the_expected_size(real):
    text = to_mermaid(hosting_view(*real, REFERENCE, DEADLINE))
    assert text.count("-->") == 27
    assert "    supplier_portal -->|api, file| erp_finance" in text


# DOT rendering (ADR-0007, decisions 1 and 6).


def test_dot_quote_escapes_backslashes_and_quotes():
    assert dot_quote('a "b" c\\d') == '"a \\"b\\" c\\\\d"'


def test_dot_of_an_empty_view_has_header_and_legend_only():
    text = to_dot(View("global", [], []))
    assert text.startswith('digraph "global" {\n    rankdir=LR;\n')
    assert "    subgraph cluster_legend {" in text
    assert text.endswith("}\n")


def test_dot_application_and_component_nodes():
    view = View(
        "end-of-life",
        [Node("app-a", "App A", APPLICATION), Node("db-1", "DB 1", IT_COMPONENT)],
        [],
    )
    text = to_dot(view)
    assert '    "app-a" [label="App A"];' in text
    assert '    "db-1" [label="DB 1", shape=cylinder];' in text


def test_dot_edges_with_and_without_label():
    view = View(
        "x",
        [Node("a", "A", APPLICATION), Node("b", "B", APPLICATION)],
        [Edge("a", "b", "api, file"), Edge("b", "a")],
    )
    text = to_dot(view)
    assert '    "a" -> "b" [label="api, file"];' in text
    assert '    "b" -> "a";' in text


def test_dot_groups_become_clusters(real):
    text = to_dot(hosting_view(*real, REFERENCE))
    assert '    subgraph cluster_data_center {\n        label="Data center";' in text
    assert (
        text.count("    subgraph cluster_") == 5
    )  # four hosting groups and the legend


def test_dot_styles_follow_the_signals(real):
    text = to_dot(hosting_view(*real, REFERENCE, DEADLINE))
    assert (
        '"data-warehouse" [label="Data warehouse", fillcolor="#f8d0d0", color="#b03030",'
        ' style="filled"];'
    ) in text
    assert (
        '"bi-reporting" [label="BI reporting", fillcolor="#fde4c0", color="#c07020",'
        ' style="filled,dashed"];'
    ) in text
    assert '"erp-finance" [label="ERP finance"];' in text


def test_dot_emphasis_on_the_focus(real):
    text = to_dot(focus_view(*real, "store-inventory", REFERENCE))
    assert '"store-inventory" [label="Store inventory", style="bold"];' in text


def test_dot_is_deterministic(real):
    first = to_dot(hosting_view(*real, REFERENCE, DEADLINE))
    second = to_dot(hosting_view(*real, REFERENCE, DEADLINE))
    assert first == second


def test_dot_of_the_curated_global_view_has_every_pair(real):
    text = to_dot(global_view(*real, REFERENCE))
    assert text.count(" -> ") == 27
    assert '"supplier-portal" -> "erp-finance" [label="api, file"];' in text
