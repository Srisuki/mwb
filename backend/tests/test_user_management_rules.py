import pytest
from fastapi import HTTPException

from app.api.users import CLIENT_ROLE_NAMES, validate_scope
from app.models import Entity, Role
from app.seed import ROLE_PERMISSIONS


def role(name: str) -> Role:
    return Role(code=name.upper().replace(" ", "_"), name=name, description="")


def test_client_management_requires_client_scope():
    assert "Client Management" in CLIENT_ROLE_NAMES
    with pytest.raises(HTTPException) as error:
        validate_scope(role("Client Management"), [])
    assert error.value.status_code == 422


def test_client_management_accepts_authorized_client_scope():
    validate_scope(role("Client Management"), [Entity(name="Authorized client")])


def test_administration_permissions_are_not_granted_to_non_admin_roles():
    administrative = {
        "USER_VIEW",
        "USER_CREATE",
        "USER_EDIT",
        "USER_ACTIVATE",
        "USER_DEACTIVATE",
        "ROLE_VIEW",
        "ROLE_MANAGE",
    }
    assert administrative <= set(ROLE_PERMISSIONS["Admin / Partner"])
    for role_name in ("Audit Manager", "Audit Staff", "Client Management"):
        assert not administrative.intersection(ROLE_PERMISSIONS[role_name])
