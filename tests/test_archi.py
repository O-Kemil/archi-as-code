"""Tests for the Archi export (ADR-0008)."""

from datetime import date
from pathlib import Path

import pytest

from archinv.archi import (
    PROPERTY_NAMES,
    Relationship,
    build_model,
    element_id,
    relationship_id,
)
from archinv.graph import build_graph
from archinv.loader import Inventory, load_inventory

INVENTORY = Path(__file__).parent.parent / "inventory"
REFERENCE = date(2026, 10, 16)


@pytest.fixture(scope="module")
def real():
    inventory = load_inventory(INVENTORY)
    return inventory, build_graph(inventory)


@pytest.fixture(scope="module")
def model(real):
    inventory, graph = real
    return build_model(inventory, graph, REFERENCE, "Maison Zola application inventory")


def by_identifier(model):
    return {e.identifier: e for e in model.elements} | {
        r.identifier: r for r in model.relationships
    }


# Step 1: the model in memory.


def test_identifiers_are_xml_names_and_unambiguous():
    assert element_id("2024") == "id-2024"
    assert relationship_id("pos-stores", "erp") != relationship_id("pos", "stores-erp")


def test_model_name_and_documentation(model):
    assert model.name == "Maison Zola application inventory"
    assert model.documentation == (
        "Produced by archinv. Reference date: 2026-10-16. 15 applications, 9 IT components."
    )


def test_one_element_per_record_with_the_mapped_type(real, model):
    inventory, _ = real
    assert len(model.elements) == len(inventory.applications) + len(
        inventory.it_components
    )
    assert by_identifier(model)["id-pos-stores"].type == "ApplicationComponent"
    assert by_identifier(model)["id-postgresql-15"].type == "SystemSoftware"


def test_application_element_fields(model):
    element = by_identifier(model)["id-bi-reporting"]
    assert element.name == "BI reporting"
    assert element.documentation == "Dashboards for management and store managers."
    assert element.properties == {
        "id": "bi-reporting",
        "technical_owner": "Data engineering team",
        "business_criticality": "administrative_service",
        "hosting": "data_center",
        "lifecycle.active": "2017-02-01",
        "lifecycle_phase": "active",
    }


def test_component_element_fields(model):
    element = by_identifier(model)["id-windows-server-2016"]
    assert element.properties["vendor"] == "Microsoft"
    assert element.properties["lifecycle.end_of_life"] == "2027-01-12"
    assert element.documentation == ""


def test_lifecycle_phase_follows_the_reference_date(real):
    inventory, graph = real
    early = build_model(inventory, graph, date(2026, 8, 1))
    assert (
        by_identifier(early)["id-transport-management"].properties["lifecycle_phase"]
        == "phase_in"
    )


def test_depends_on_becomes_serving_from_the_target_to_the_declaring_application(model):
    assert by_identifier(model)["rel-erp-finance_supplier-portal"] == Relationship(
        "rel-erp-finance_supplier-portal",
        "Serving",
        "id-erp-finance",
        "id-supplier-portal",
        "api: Purchase orders and their status.\nfile: Nightly batch upload of supplier invoices.",
        {"dependency_types": "api, file"},
    )


def test_runs_on_becomes_serving_from_the_component_to_the_application(model):
    relationship = by_identifier(model)["rel-postgresql-15_ecommerce-site"]
    assert (relationship.source, relationship.target) == (
        "id-postgresql-15",
        "id-ecommerce-site",
    )
    assert relationship.properties == {}


def test_one_relationship_per_edge_and_unique_identifiers(real, model):
    _, graph = real
    assert len(model.relationships) == graph.number_of_edges()
    identifiers = [e.identifier for e in model.elements]
    identifiers += [r.identifier for r in model.relationships]
    assert len(identifiers) == len(set(identifiers))


def test_every_property_used_is_declared(model):
    used = {key for e in model.elements for key in e.properties}
    used |= {key for r in model.relationships for key in r.properties}
    assert used <= set(PROPERTY_NAMES)
    assert model.property_names == PROPERTY_NAMES


@pytest.mark.parametrize(
    ("category", "expected"),
    [
        ("software", "SystemSoftware"),
        ("hardware", "Device"),
        ("service", "TechnologyService"),
    ],
)
def test_component_category_mapping(make_component, category, expected):
    inventory = Inventory({}, {"c": make_component("c", category=category)})
    assert (
        build_model(inventory, build_graph(inventory), REFERENCE).elements[0].type
        == expected
    )


def test_default_model_name():
    empty = Inventory({}, {})
    assert (
        build_model(empty, build_graph(empty), REFERENCE).name
        == "Application inventory"
    )
