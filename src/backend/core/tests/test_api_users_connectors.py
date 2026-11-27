"""The users API and `allowed_connectors`: the standing opt-in, one slug per connector."""

import pytest
from rest_framework.test import APIClient

from core.factories import UserFactory
from core.feature_flags.flags import FeatureToggle

from chat.tests.connectors.declarations import datagouv_declaration, sofia_declaration

pytestmark = pytest.mark.django_db


@pytest.fixture(name="declared", autouse=True)
def declared_fixture(settings, feature_flags):
    """The deployment offers data.gouv (gated to a cohort) and SofIA (open to everyone)."""
    feature_flags.datagouv_connector = FeatureToggle.ENABLED
    settings.MCP_CONNECTORS = [datagouv_declaration(), sofia_declaration()]


def _patch(user, allowed_connectors):
    """PATCH the user's opt-ins as themselves."""
    client = APIClient()
    client.force_login(user)
    return client.patch(
        f"/api/v1.0/users/{user.pk!s}/",
        {"allowed_connectors": allowed_connectors},
        format="json",
    )


def test_the_opt_ins_are_part_of_the_user():
    """The frontend reads them off /users/me/."""
    user = UserFactory(allowed_connectors=["sofia"])
    client = APIClient()
    client.force_login(user)

    response = client.get("/api/v1.0/users/me/")

    assert response.status_code == 200
    assert response.json()["allowed_connectors"] == ["sofia"]


def test_a_new_user_has_opted_in_to_nothing():
    """Connectors are opt-in."""
    assert UserFactory().allowed_connectors == []


def test_offered_connectors_can_be_switched_on():
    """Every offered slug is accepted, in the order given."""
    user = UserFactory()

    response = _patch(user, ["sofia", "datagouv"])

    assert response.status_code == 200
    user.refresh_from_db()
    assert user.allowed_connectors == ["sofia", "datagouv"]


def test_a_connector_can_be_switched_off():
    """Leaving a slug out switches its connector off."""
    user = UserFactory(allowed_connectors=["sofia", "datagouv"])

    assert _patch(user, ["datagouv"]).status_code == 200

    user.refresh_from_db()
    assert user.allowed_connectors == ["datagouv"]


def test_a_slug_given_twice_is_kept_once():
    """A list of slugs, not of clicks."""
    user = UserFactory()

    assert _patch(user, ["sofia", "sofia"]).status_code == 200

    user.refresh_from_db()
    assert user.allowed_connectors == ["sofia"]


@pytest.mark.parametrize("slug", ["github", "Sofia", ""])
def test_a_slug_the_deployment_does_not_offer_is_refused(slug):
    """Nobody can opt in to a connector that does not exist."""
    user = UserFactory()

    response = _patch(user, [slug])

    assert response.status_code == 400
    assert "allowed_connectors" in response.json()
    user.refresh_from_db()
    assert user.allowed_connectors == []


def test_a_connector_outside_the_user_cohort_is_refused(feature_flags):
    """Offered means offered to this user: the cohort applies to the opt-in too."""
    feature_flags.datagouv_connector = FeatureToggle.DISABLED
    user = UserFactory()

    assert _patch(user, ["datagouv"]).status_code == 400


def test_a_slug_the_user_already_had_is_kept(settings):
    """A connector taken offline for a while keeps its users' consent."""
    settings.MCP_CONNECTORS = [sofia_declaration()]
    user = UserFactory(allowed_connectors=["datagouv"])

    response = _patch(user, ["datagouv", "sofia"])

    assert response.status_code == 200
    user.refresh_from_db()
    assert user.allowed_connectors == ["datagouv", "sofia"]


@pytest.mark.parametrize("value", ["sofia", [3], None, {"sofia": True}])
def test_a_value_that_is_not_a_list_of_slugs_is_refused(value):
    """One JSON array of strings."""
    user = UserFactory()

    assert _patch(user, value).status_code == 400
