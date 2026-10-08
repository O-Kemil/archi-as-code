"""Record models for the inventory, as specified in ADR-0001."""

from datetime import date
from enum import StrEnum
from itertools import pairwise
from typing import Annotated, Self

from pydantic import (
    BaseModel,
    ConfigDict,
    StringConstraints,
    ValidationInfo,
    field_validator,
    model_validator,
)

SLUG_PATTERN = r"^[a-z0-9]+(-[a-z0-9]+)*$"

Slug = Annotated[str, StringConstraints(pattern=SLUG_PATTERN)]
"""A kebab-case identifier, as defined in ADR-0001."""

Text = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]
"""A required piece of text: surrounding whitespace is removed, empty is rejected."""


class StrictModel(BaseModel):
    """Base class for every record model: unknown fields are rejected."""

    model_config = ConfigDict(extra="forbid")


class LifecyclePhase(StrEnum):
    """The five lifecycle phases, in order. Values match the Lifecycle field names."""

    PLAN = "plan"
    PHASE_IN = "phase_in"
    ACTIVE = "active"
    PHASE_OUT = "phase_out"
    END_OF_LIFE = "end_of_life"


class Lifecycle(StrictModel):
    """Dates at which a record enters each phase. All optional, in chronological order."""

    plan: date | None = None
    phase_in: date | None = None
    active: date | None = None
    phase_out: date | None = None
    end_of_life: date | None = None

    def dated_phases(self) -> list[tuple[LifecyclePhase, date]]:
        """Return the phases that have a date, in lifecycle order."""
        dated = []
        for phase in LifecyclePhase:
            value = getattr(self, phase.value)
            if value is not None:
                dated.append((phase, value))
        return dated

    @model_validator(mode="after")
    def check_chronological_order(self) -> Self:
        for (earlier, earlier_date), (later, later_date) in pairwise(
            self.dated_phases()
        ):
            if later_date < earlier_date:
                raise ValueError(
                    f"{later.value} ({later_date}) is before {earlier.value} ({earlier_date})"
                )
        return self

    def current_phase(self, reference: date) -> LifecyclePhase | None:
        """Return the latest phase started on or before the reference date."""
        current = None
        for phase, value in self.dated_phases():
            if value <= reference:
                current = phase
        return current


class DependencyType(StrEnum):
    """How an application is coupled to the one it depends on."""

    API = "api"
    FILE = "file"
    DATABASE = "database"
    EVENT = "event"


class Dependency(StrictModel):
    """A link declared by the consumer: this application needs another one to work.

    Self-dependency and duplicate targets are checked by Application;
    the existence of the target is checked by the loader.
    """

    application: Slug
    type: DependencyType
    description: str | None = None


class ITComponentCategory(StrEnum):
    """The three LeanIX meta model v3 subtypes (ADR-0001)."""

    SOFTWARE = "software"
    HARDWARE = "hardware"
    SERVICE = "service"


class ITComponent(StrictModel):
    """A technology an application runs on, one record per version.

    The rule "id equals the file name" is checked by the loader, which knows the path.
    """

    id: Slug
    name: Text
    category: ITComponentCategory
    vendor: str | None = None
    version: str | None = None
    lifecycle: Lifecycle | None = None


class BusinessCriticality(StrEnum):
    """How much the business suffers if the application stops (LeanIX levels)."""

    MISSION_CRITICAL = "mission_critical"
    BUSINESS_CRITICAL = "business_critical"
    BUSINESS_OPERATIONAL = "business_operational"
    ADMINISTRATIVE_SERVICE = "administrative_service"


class Hosting(StrEnum):
    """Where the application runs (ADR-0001, secondary choices)."""

    DATA_CENTER = "data_center"
    CLOUD = "cloud"
    SAAS = "saas"
    STORE = "store"


class Application(StrictModel):
    """An application of the portfolio.

    The rule "id equals the file name" and the existence of the ids listed in
    depends_on and it_components are checked by the loader.
    """

    id: Slug
    name: Text
    description: Text
    business_owner: str | None = None
    technical_owner: str | None = None
    business_criticality: BusinessCriticality
    hosting: Hosting
    lifecycle: Lifecycle
    depends_on: list[Dependency] = []
    it_components: list[Slug] = []

    @field_validator("lifecycle")
    @classmethod
    def check_at_least_one_date(cls, lifecycle: Lifecycle) -> Lifecycle:
        if not lifecycle.dated_phases():
            raise ValueError("an application lifecycle needs at least one date")
        return lifecycle

    @field_validator("depends_on")
    @classmethod
    def check_targets(
        cls, dependencies: list[Dependency], info: ValidationInfo
    ) -> list[Dependency]:
        # Several links to the same application are allowed when their types differ
        # (ADR-0001, amendment of 2026-10-08). The same (target, type) pair is not.
        seen = set()
        for dependency in dependencies:
            target = dependency.application
            if target == info.data.get("id"):
                raise ValueError(f"{target} depends on itself")
            link = (target, dependency.type)
            if link in seen:
                raise ValueError(f"{target} ({dependency.type.value}) is listed twice")
            seen.add(link)
        return dependencies

    @field_validator("it_components")
    @classmethod
    def check_no_duplicate_component(cls, components: list[str]) -> list[str]:
        seen = set()
        for component in components:
            if component in seen:
                raise ValueError(f"{component} is listed twice")
            seen.add(component)
        return components
