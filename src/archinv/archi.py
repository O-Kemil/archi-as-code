"""Archi export, as specified in ADR-0008."""

from dataclasses import dataclass, field
from datetime import date

import networkx as nx

from archinv.graph import DEPENDS_ON
from archinv.loader import Inventory
from archinv.models import (
    Application,
    ITComponent,
    ITComponentCategory,
    Lifecycle,
    LifecyclePhase,
)

ELEMENT_TYPES = {
    ITComponentCategory.SOFTWARE: "SystemSoftware",
    ITComponentCategory.HARDWARE: "Device",
    ITComponentCategory.SERVICE: "TechnologyService",
}
# Declared once in propertyDefinitions, in this order (ADR-0008, decision 1).
PROPERTY_NAMES = [
    "id",
    "business_owner",
    "technical_owner",
    "business_criticality",
    "hosting",
    *[f"lifecycle.{phase.value}" for phase in LifecyclePhase],
    "lifecycle_phase",
    "vendor",
    "version",
    "dependency_types",
]
DEFAULT_MODEL_NAME = "Application inventory"


@dataclass(frozen=True)
class Element:
    identifier: str
    type: str  # the xsi:type: ApplicationComponent, SystemSoftware, Device, TechnologyService
    name: str
    documentation: str = ""
    properties: dict[str, str] = field(default_factory=dict)


@dataclass(frozen=True)
class Relationship:
    identifier: str
    type: str  # always Serving in v1
    source: str
    target: str
    documentation: str = ""
    properties: dict[str, str] = field(default_factory=dict)


@dataclass(frozen=True)
class Model:
    name: str
    documentation: str
    elements: list[Element]
    relationships: list[Relationship]
    property_names: list[str]


def element_id(record_id: str) -> str:
    return f"id-{record_id}"


def relationship_id(source_id: str, target_id: str) -> str:
    """Underscore separator: slugs contain hyphens, never underscores (ADR-0008, decision 3)."""
    return f"rel-{source_id}_{target_id}"


def lifecycle_properties(
    lifecycle: Lifecycle | None, reference: date
) -> dict[str, str]:
    properties = {}
    if lifecycle is None:
        return properties
    for phase, value in lifecycle.dated_phases():
        properties[f"lifecycle.{phase.value}"] = value.isoformat()
    current = lifecycle.current_phase(reference)
    if current:
        properties["lifecycle_phase"] = current.value
    return properties


def application_element(application: Application, reference: date) -> Element:
    properties = {"id": application.id}
    if application.business_owner:
        properties["business_owner"] = application.business_owner
    if application.technical_owner:
        properties["technical_owner"] = application.technical_owner
    properties["business_criticality"] = application.business_criticality.value
    properties["hosting"] = application.hosting.value
    properties.update(lifecycle_properties(application.lifecycle, reference))
    return Element(
        element_id(application.id),
        "ApplicationComponent",
        application.name,
        application.description,
        properties,
    )


def component_element(component: ITComponent, reference: date) -> Element:
    properties = {"id": component.id}
    if component.vendor:
        properties["vendor"] = component.vendor
    if component.version:
        properties["version"] = component.version
    properties.update(lifecycle_properties(component.lifecycle, reference))
    return Element(
        element_id(component.id),
        ELEMENT_TYPES[component.category],
        component.name,
        "",
        properties,
    )


def build_model(
    inventory: Inventory,
    graph: nx.DiGraph,
    reference: date,
    name: str = DEFAULT_MODEL_NAME,
) -> Model:
    """Every record as an element, every edge as a Serving relationship (ADR-0008)."""
    elements = [
        application_element(a, reference)
        for a in sorted(inventory.applications.values(), key=lambda r: r.id)
    ]
    elements += [
        component_element(c, reference)
        for c in sorted(inventory.it_components.values(), key=lambda r: r.id)
    ]
    relationships = []
    for declaring, target, data in sorted(
        graph.edges(data=True), key=lambda e: (e[0], e[1])
    ):
        # Serving goes from what is needed to what needs it: the target serves the declaring one.
        source, destination = element_id(target), element_id(declaring)
        identifier = relationship_id(target, declaring)
        if data["kind"] == DEPENDS_ON:
            types = ", ".join(t.value for t in data["types"])
            lines = [
                f"{d.type.value}: {d.description}" if d.description else d.type.value
                for d in data["dependencies"]
            ]
            relationships.append(
                Relationship(
                    identifier,
                    "Serving",
                    source,
                    destination,
                    "\n".join(lines),
                    {"dependency_types": types},
                )
            )
        else:
            relationships.append(
                Relationship(identifier, "Serving", source, destination)
            )
    documentation = (
        f"Produced by archinv. Reference date: {reference.isoformat()}."
        f" {len(inventory.applications)} applications, {len(inventory.it_components)} IT components."
    )
    return Model(name, documentation, elements, relationships, PROPERTY_NAMES)
