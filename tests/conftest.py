"""Fixtures shared by the test modules: factories for in-memory records."""

import pytest

from archinv.models import Application, ITComponent


@pytest.fixture
def make_application():
    """Build a valid application with the given id; depends_on takes (target, type) pairs."""

    def factory(
        record_id,
        depends_on=(),
        it_components=(),
        hosting="cloud",
        business_owner="Owner",
    ):
        return Application(
            id=record_id,
            name=record_id,
            description="d",
            business_owner=business_owner,
            business_criticality="administrative_service",
            hosting=hosting,
            lifecycle={"active": "2020-01-01"},
            depends_on=[{"application": t, "type": k} for t, k in depends_on],
            it_components=list(it_components),
        )

    return factory


@pytest.fixture
def make_component():
    """Build a valid IT component; lifecycle is None, a dict, or set from end_of_life."""

    def factory(record_id, end_of_life=None, lifecycle=None):
        if end_of_life is not None:
            lifecycle = {"end_of_life": end_of_life}
        return ITComponent(
            id=record_id, name=record_id, category="software", lifecycle=lifecycle
        )

    return factory
