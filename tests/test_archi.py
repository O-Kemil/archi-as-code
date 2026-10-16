"""Tests for the Archi export (ADR-0008)."""

import os
import urllib.request
import xml.etree.ElementTree as ET
from datetime import date
from pathlib import Path

import pytest
import xmlschema

from archinv.archi import (
    NAMESPACE,
    PROPERTY_NAMES,
    Relationship,
    build_model,
    element_id,
    relationship_id,
    to_xml,
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


def test_model_name_and_documentation(real, model):
    inventory, _ = real
    assert model.name == "Maison Zola application inventory"
    assert model.documentation == (
        "Produced by archinv. Reference date: 2026-10-16."
        f" {len(inventory.applications)} applications,"
        f" {len(inventory.it_components)} IT components."
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


# Step 2: Open Exchange Format XML.

NS = {"a": NAMESPACE}


def local(tag):
    return tag.split("}")[1]


def property_values(node, root):
    """Property name -> value, resolving propertyDefinitionRef against the definitions."""
    names = {
        d.get("identifier"): d.find("a:name", NS).text
        for d in root.find("a:propertyDefinitions", NS)
    }
    return {
        names[p.get("propertyDefinitionRef")]: p.find("a:value", NS).text
        for p in node.findall("a:properties/a:property", NS)
    }


def test_xml_declaration_namespace_and_order(model):
    text = to_xml(model)
    assert text.startswith(
        "<?xml version='1.0' encoding='utf-8'?>\n"
        '<model xmlns="http://www.opengroup.org/xsd/archimate/3.0/"'
    )
    root = ET.fromstring(text)
    assert root.get("identifier") == "archinv-model"
    assert [local(child.tag) for child in root] == [
        "name",
        "documentation",
        "elements",
        "relationships",
        "propertyDefinitions",
    ]
    assert root.find("a:name", NS).text == "Maison Zola application inventory"


def test_xml_element_has_type_name_documentation_and_properties(model):
    root = ET.fromstring(to_xml(model))
    node = root.find("a:elements/a:element[@identifier='id-bi-reporting']", NS)
    assert (
        node.get("{http://www.w3.org/2001/XMLSchema-instance}type")
        == "ApplicationComponent"
    )
    assert node.find("a:name", NS).text == "BI reporting"
    assert (
        node.find("a:documentation", NS).text
        == "Dashboards for management and store managers."
    )
    assert property_values(node, root) == {
        "id": "bi-reporting",
        "technical_owner": "Data engineering team",
        "business_criticality": "administrative_service",
        "hosting": "data_center",
        "lifecycle.active": "2017-02-01",
        "lifecycle_phase": "active",
    }


def test_xml_relationship_attributes(model):
    root = ET.fromstring(to_xml(model))
    node = root.find(
        "a:relationships/a:relationship[@identifier='rel-erp-finance_supplier-portal']",
        NS,
    )
    assert node.get("source") == "id-erp-finance"
    assert node.get("target") == "id-supplier-portal"
    assert node.get("{http://www.w3.org/2001/XMLSchema-instance}type") == "Serving"
    assert node.find("a:documentation", NS).text == (
        "api: Purchase orders and their status.\nfile: Nightly batch upload of supplier invoices."
    )
    assert property_values(node, root) == {"dependency_types": "api, file"}


def test_xml_property_definitions_follow_property_names(model):
    root = ET.fromstring(to_xml(model))
    definitions = root.find("a:propertyDefinitions", NS)
    assert [d.get("identifier") for d in definitions] == [
        f"propid-{i + 1}" for i in range(len(PROPERTY_NAMES))
    ]
    assert [d.find("a:name", NS).text for d in definitions] == PROPERTY_NAMES
    assert {d.get("type") for d in definitions} == {"string"}


def test_xml_omits_empty_documentation(model):
    root = ET.fromstring(to_xml(model))
    component = root.find("a:elements/a:element[@identifier='id-postgresql-15']", NS)
    assert component.find("a:documentation", NS) is None
    runs_on = root.find(
        "a:relationships/a:relationship[@identifier='rel-postgresql-15_ecommerce-site']",
        NS,
    )
    assert runs_on.find("a:documentation", NS) is None
    assert runs_on.find("a:properties", NS) is None


def test_xml_escapes_special_characters(make_application):
    application = make_application("a").model_copy(update={"name": 'R&D "core" <beta>'})
    inventory = Inventory({"a": application}, {})
    text = to_xml(build_model(inventory, build_graph(inventory), REFERENCE))
    assert "&amp;" in text
    assert "<beta>" not in text
    root = ET.fromstring(text)
    assert root.find("a:elements/a:element/a:name", NS).text == 'R&D "core" <beta>'


def test_xml_is_deterministic(model):
    assert to_xml(model) == to_xml(model)


def test_xml_of_an_empty_inventory_is_well_formed():
    empty = Inventory({}, {})
    root = ET.fromstring(to_xml(build_model(empty, build_graph(empty), REFERENCE)))
    assert len(root.find("a:elements", NS)) == 0
    assert len(root.find("a:relationships", NS)) == 0
    assert len(root.find("a:propertyDefinitions", NS)) == len(PROPERTY_NAMES)


# Step 3, level 1: the export is valid against the official schema (ADR-0008, decision 6).

XSD_BASE = "https://www.opengroup.org/xsd/archimate/3.1/"
XSD_FILES = ["archimate3_Model.xsd", "archimate3_View.xsd", "archimate3_Diagram.xsd"]
XSD_CACHE = Path(__file__).parent.parent / ".cache" / "archimate-xsd"  # git-ignored


@pytest.fixture(scope="module")
def xsd_schema():
    """The Open Group schema, from the cache or downloaded.

    In the CI (CI=true) a failed download fails the tests; on a laptop they are skipped.
    """
    missing = [name for name in XSD_FILES if not (XSD_CACHE / name).exists()]
    if missing:
        XSD_CACHE.mkdir(parents=True, exist_ok=True)
        try:
            for name in missing:
                with urllib.request.urlopen(XSD_BASE + name, timeout=20) as response:
                    (XSD_CACHE / name).write_bytes(response.read())
        except OSError as error:
            message = (
                f"could not download the ArchiMate XSD files ({error}); fetch them by hand:"
                f" for f in {' '.join(XSD_FILES)}; do curl -o {XSD_CACHE}/$f {XSD_BASE}$f; done"
            )
            if os.environ.get("CI") == "true":
                pytest.fail(message)
            pytest.skip(message)
    return xmlschema.XMLSchema(XSD_CACHE / "archimate3_Model.xsd")


@pytest.fixture
def every_category_inventory(make_application, make_component):
    return Inventory(
        {"a": make_application("a", it_components=["s", "h", "t"])},
        {
            "s": make_component("s", category="software"),
            "h": make_component("h", category="hardware"),
            "t": make_component("t", category="service"),
        },
    )


def test_export_of_the_curated_data_set_is_valid_against_the_xsd(model, xsd_schema):
    xsd_schema.validate(to_xml(model))


def test_export_with_every_component_category_is_valid_against_the_xsd(
    every_category_inventory, xsd_schema
):
    inventory = every_category_inventory
    xsd_schema.validate(
        to_xml(build_model(inventory, build_graph(inventory), REFERENCE))
    )


def test_an_invalid_document_is_rejected_by_the_schema(xsd_schema):
    # The schema is really applied: an unknown element type fails.
    empty = Inventory({}, {})
    text = to_xml(build_model(empty, build_graph(empty), REFERENCE))
    broken = text.replace(
        "<elements />",
        '<elements><element identifier="x" xsi:type="Nope">'
        '<name xml:lang="en">x</name></element></elements>',
    )
    assert broken != text
    with pytest.raises(xmlschema.XMLSchemaException):
        xsd_schema.validate(broken)


# Step 3, level 2: every relationship is allowed by Archi's matrix, which the XSD does not
# enforce. Source: Archi relationships.xml and relationships-keys.xml, read on 2026-10-16
# (https://github.com/archimatetool/archi/tree/master/com.archimatetool.model/model).
# Serving is the letter "v": ApplicationComponent -> ApplicationComponent "cfgorstv";
# SystemSoftware and Device -> ApplicationComponent "fortv"; TechnologyService ->
# ApplicationComponent "fotv".
ALLOWED_RELATIONSHIPS = {
    ("ApplicationComponent", "ApplicationComponent", "Serving"),
    ("SystemSoftware", "ApplicationComponent", "Serving"),
    ("Device", "ApplicationComponent", "Serving"),
    ("TechnologyService", "ApplicationComponent", "Serving"),
}


def relationship_triples(model):
    types = {e.identifier: e.type for e in model.elements}
    return {(types[r.source], types[r.target], r.type) for r in model.relationships}


def test_every_relationship_of_the_curated_data_set_is_allowed_by_archi(model):
    assert relationship_triples(model) <= ALLOWED_RELATIONSHIPS


def test_every_component_category_gives_an_allowed_relationship(
    every_category_inventory,
):
    inventory = every_category_inventory
    triples = relationship_triples(
        build_model(inventory, build_graph(inventory), REFERENCE)
    )
    assert triples == ALLOWED_RELATIONSHIPS - {
        ("ApplicationComponent", "ApplicationComponent", "Serving")
    }
