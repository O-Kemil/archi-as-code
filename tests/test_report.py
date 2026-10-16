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
    render,
    section,
    table,
    without_business_owner,
    without_it_component,
)

INVENTORY = Path(__file__).parent.parent / "inventory"
EXAMPLE = Path(__file__).parent.parent / "docs" / "report-example.md"
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
    apps = {
        a.id: a
        for a in [
            make_application("z", business_owner=None),
            make_application("y", business_owner=None),
        ]
    }
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


# Markdown rendering (ADR-0006, decision 1).


def test_table_renders_header_separator_and_rows():
    assert table(["A", "B"], [(1, "x"), (2, "y")]) == [
        "| A | B |",
        "|---|---|",
        "| 1 | x |",
        "| 2 | y |",
    ]


def test_table_escapes_pipes_in_cells():
    assert table(["A"], [("x | y",)])[2] == "| x \\| y |"


def test_section_without_body_says_none():
    assert section("Title", []) == ["", "## Title", "", "None."]


def test_render_starts_with_the_title_and_the_reference_date(real):
    inventory, graph = real
    text = render(inventory, graph, REFERENCE)
    assert text.startswith(
        "# Anomaly report\n\n"
        f"Reference date: 2026-10-13. Inventory: {len(inventory.applications)} applications,"
        f" {len(inventory.it_components)} IT components.\n"
    )


def test_render_mentions_the_deadline_only_when_given(real):
    inventory, graph = real
    without = render(inventory, graph, REFERENCE)
    with_deadline = render(inventory, graph, REFERENCE, DEADLINE)
    assert "Deadline" not in without
    assert "## IT components reaching end of life before 2028-03-31" not in without
    assert "Deadline: 2028-03-31." in with_deadline
    assert (
        "| IT components reaching end of life before 2028-03-31 | 2 |" in with_deadline
    )


def test_render_lists_the_sections_in_the_order_of_the_adr(real):
    inventory, graph = real
    text = render(inventory, graph, REFERENCE, DEADLINE)
    assert [line for line in text.splitlines() if line.startswith("## ")] == [
        "## Summary",
        "## Applications without business owner",
        "## Circular dependencies",
        "## IT components past end of life",
        "## IT components reaching end of life before 2028-03-31",
        "## Applications without IT component",
        "## Most depended-upon applications",
    ]


def test_render_shows_the_expected_anomalies(real):
    inventory, graph = real
    text = render(inventory, graph, REFERENCE, DEADLINE)
    assert "| bi-reporting | BI reporting | Data engineering team |" in text
    assert (
        "- order-management -> store-inventory -> warehouse-management -> order-management"
        in text
    )
    assert (
        "| windows-server-2012-r2 | Windows Server 2012 R2 | 2023-10-10 |"
        " pos-stores, price-label-printing |"
    ) in text
    assert (
        "| postgresql-15 | PostgreSQL 15 | 2027-11-11 |"
        " ecommerce-site, order-management, supplier-portal |"
    ) in text
    assert "| erp-finance | 6 |" in text


def test_render_says_none_for_an_empty_section(real):
    inventory, graph = real
    assert "## Applications without IT component\n\nNone.\n" in render(
        inventory, graph, REFERENCE
    )


def test_render_is_deterministic(real):
    inventory, graph = real
    assert render(inventory, graph, REFERENCE, DEADLINE) == render(
        inventory, graph, REFERENCE, DEADLINE
    )


def test_render_ends_with_a_newline(real):
    inventory, graph = real
    assert render(inventory, graph, REFERENCE).endswith("|\n")


def test_render_of_an_empty_inventory():
    empty = Inventory({}, {})
    text = render(empty, build_graph(empty), REFERENCE)
    assert "Inventory: 0 applications, 0 IT components." in text
    assert text.count("None.") == 5


# The committed example is a golden file (ADR-0006, decision 5).


def test_the_committed_example_is_the_report_of_the_curated_data_set(real):
    inventory, graph = real
    text = EXAMPLE.read_text(encoding="utf-8")
    assert text.startswith("> Example of the anomaly report")
    assert text.endswith(render(inventory, graph, REFERENCE, DEADLINE)), (
        "regenerate docs/report-example.md, see its header"
    )
