from app.main import app
from app.seed import ROLE_PERMISSIONS


def test_required_production_routes_are_registered():
    routes = {(method, route.path) for route in app.routes for method in route.methods or []}
    required = {
        ("POST", "/api/auth/login"),
        ("POST", "/api/auth/logout"),
        ("GET", "/api/auth/me"),
        ("POST", "/api/auth/change-password"),
        ("GET", "/api/users"),
        ("POST", "/api/users"),
        ("PATCH", "/api/users/{user_id}"),
        ("GET", "/api/users/{user_id}"),
        ("POST", "/api/users/{user_id}/activate"),
        ("POST", "/api/users/{user_id}/deactivate"),
        ("GET", "/api/users/{user_id}/permissions"),
        ("GET", "/api/users/{user_id}/clients"),
        ("PUT", "/api/users/{user_id}/clients"),
        ("GET", "/api/roles"),
        ("GET", "/api/permissions"),
        ("GET", "/api/entities"),
        ("POST", "/api/entities"),
        ("PATCH", "/api/entities/{entity_id}"),
        ("GET", "/api/audit-plans"),
        ("POST", "/api/audit-plans"),
        ("POST", "/api/audit-plans/full-month"),
        ("POST", "/api/audit-plans/carry-forward"),
        ("GET", "/api/observations"),
        ("POST", "/api/observations"),
        ("PATCH", "/api/observations/{observation_id}"),
        ("GET", "/api/observations/{observation_id}/history"),
        ("POST", "/api/observations/{observation_id}/replies"),
        ("POST", "/api/reports/generate"),
        ("POST", "/api/reports/{report_id}/approve"),
        ("POST", "/api/documents/upload"),
        ("GET", "/api/documents/{document_id}/download"),
        ("DELETE", "/api/documents/{document_id}"),
        ("POST", "/api/migrations/legacy-json"),
        ("GET", "/api/dashboard/summary"),
        ("GET", "/live"),
        ("GET", "/ready"),
        ("GET", "/health"),
    }
    assert required <= routes


def test_role_matrix_separates_administration_approval_and_client_actions():
    admin = set(ROLE_PERMISSIONS["Admin / Partner"])
    manager = set(ROLE_PERMISSIONS["Audit Manager"])
    staff = set(ROLE_PERMISSIONS["Audit Staff"])
    client = set(ROLE_PERMISSIONS["Client Management"])
    assert {"MANAGE_USERS", "APPROVE_REPORT", "LOCK_REPORT"} <= admin
    assert "APPROVE_REPORT" in manager and "MANAGE_USERS" not in manager
    assert "CREATE_OBSERVATION" in staff and "APPROVE_REPORT" not in staff
    assert "CREATE_CLIENT_REPLY" in client
    assert not ({"CREATE_OBSERVATION", "MANAGE_ENTITIES", "APPROVE_REPORT"} & client)
    assert {"USER_VIEW", "USER_CREATE", "USER_EDIT", "USER_ACTIVATE", "USER_DEACTIVATE"} <= admin
    assert not ({"USER_VIEW", "USER_CREATE", "USER_EDIT"} & manager)
