"""Expand database-backed user and role administration.

Revision ID: 0004
Revises: 0003
"""

import uuid

import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect
from sqlalchemy.dialects import postgresql

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None

PERMISSIONS = [
    "USER_VIEW", "USER_CREATE", "USER_EDIT", "USER_ACTIVATE", "USER_DEACTIVATE",
    "ROLE_VIEW", "ROLE_MANAGE", "CLIENT_VIEW", "CLIENT_MANAGE",
    "AUDIT_PLAN_VIEW", "AUDIT_PLAN_CREATE", "AUDIT_PLAN_EDIT", "AUDIT_PLAN_ASSIGN",
    "AUDIT_EXECUTE", "OBSERVATION_VIEW", "OBSERVATION_CREATE", "OBSERVATION_EDIT",
    "MANAGEMENT_RESPONSE_VIEW", "MANAGEMENT_RESPONSE_CREATE", "REPORT_VIEW",
    "REPORT_GENERATE", "REPORT_APPROVE", "REPORT_LOCK", "DOCUMENT_VIEW",
    "DOCUMENT_UPLOAD", "AUDIT_HISTORY_VIEW", "SYSTEM_SETTINGS_MANAGE",
]
ROLE_PERMISSION_CODES = {
    "Audit Manager": ["CLIENT_VIEW", "AUDIT_PLAN_VIEW", "AUDIT_PLAN_CREATE", "AUDIT_PLAN_EDIT", "AUDIT_PLAN_ASSIGN", "AUDIT_EXECUTE", "OBSERVATION_VIEW", "OBSERVATION_CREATE", "OBSERVATION_EDIT", "MANAGEMENT_RESPONSE_VIEW", "REPORT_VIEW", "REPORT_GENERATE", "REPORT_APPROVE", "REPORT_LOCK", "DOCUMENT_VIEW", "DOCUMENT_UPLOAD", "AUDIT_HISTORY_VIEW", "SYSTEM_SETTINGS_MANAGE"],
    "Audit Staff": ["CLIENT_VIEW", "AUDIT_PLAN_VIEW", "AUDIT_EXECUTE", "OBSERVATION_VIEW", "OBSERVATION_CREATE", "OBSERVATION_EDIT", "MANAGEMENT_RESPONSE_VIEW", "REPORT_VIEW", "REPORT_GENERATE", "DOCUMENT_VIEW", "DOCUMENT_UPLOAD"],
    "Client Management": ["CLIENT_VIEW", "OBSERVATION_VIEW", "MANAGEMENT_RESPONSE_VIEW", "MANAGEMENT_RESPONSE_CREATE", "REPORT_VIEW", "DOCUMENT_VIEW", "DOCUMENT_UPLOAD", "UPLOAD_DOCUMENT"],
}


def upgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)
    user_columns = {column["name"] for column in inspector.get_columns("users")}
    role_columns = {column["name"] for column in inspector.get_columns("roles")}
    for name, column in {
        "mobile": sa.Column("mobile", sa.String(length=30), nullable=True),
        "is_verified": sa.Column("is_verified", sa.Boolean(), nullable=False, server_default=sa.false()),
        "created_by_id": sa.Column("created_by_id", postgresql.UUID(as_uuid=True), nullable=True),
        "updated_by_id": sa.Column("updated_by_id", postgresql.UUID(as_uuid=True), nullable=True),
    }.items():
        if name not in user_columns:
            op.add_column("users", column)
    if "created_by_id" not in user_columns:
        op.create_foreign_key("fk_users_created_by", "users", "users", ["created_by_id"], ["id"])
    if "updated_by_id" not in user_columns:
        op.create_foreign_key("fk_users_updated_by", "users", "users", ["updated_by_id"], ["id"])
    for name, column in {
        "description": sa.Column("description", sa.String(length=255), nullable=False, server_default=""),
        "is_system_role": sa.Column("is_system_role", sa.Boolean(), nullable=False, server_default=sa.true()),
        "is_active": sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
    }.items():
        if name not in role_columns:
            op.add_column("roles", column)
    if "code" not in role_columns:
        op.add_column("roles", sa.Column("code", sa.String(length=80), nullable=True))
    if "user_roles" not in inspector.get_table_names():
        op.create_table(
            "user_roles",
            sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
            sa.Column("role_id", postgresql.UUID(as_uuid=True), nullable=False),
            sa.ForeignKeyConstraint(["role_id"], ["roles.id"], ondelete="CASCADE"),
            sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
            sa.PrimaryKeyConstraint("user_id", "role_id"),
        )
    bind.execute(sa.text("UPDATE roles SET name='Client Management' WHERE name='Client / Management'"))
    for role_name, code in {
        "Admin / Partner": "ADMIN_PARTNER",
        "Audit Manager": "AUDIT_MANAGER",
        "Audit Staff": "AUDIT_STAFF",
        "Client Management": "CLIENT_MANAGEMENT",
    }.items():
        bind.execute(
            sa.text("UPDATE roles SET code=:code WHERE name=:name"),
            {"name": role_name, "code": code},
        )
    if "code" not in role_columns:
        bind.execute(
            sa.text("UPDATE roles SET code=upper(regexp_replace(name, '[^a-zA-Z0-9]+', '_', 'g')) WHERE code IS NULL")
        )
        op.alter_column("roles", "code", nullable=False)
        op.create_unique_constraint("uq_roles_code", "roles", ["code"])
    for role_name, description in {
        "Admin / Partner": "Full administration and audit authority",
        "Audit Manager": "Plans, assigns, reviews, reports, and views audit history",
        "Audit Staff": "Executes assigned audits and maintains observations and evidence",
        "Client Management": "Responds to observations within assigned client scope",
    }.items():
        bind.execute(
            sa.text("UPDATE roles SET description=:description, is_system_role=true, is_active=true WHERE name=:name"),
            {"name": role_name, "description": description},
        )
    bind.execute(sa.text("INSERT INTO user_roles (user_id, role_id) SELECT id, role_id FROM users ON CONFLICT DO NOTHING"))
    existing = {row[0] for row in bind.execute(sa.text("SELECT code FROM permissions"))}
    for code in PERMISSIONS:
        if code not in existing:
            bind.execute(
                sa.text("INSERT INTO permissions (id, code, description) VALUES (:id, :code, :description)"),
                {"id": uuid.uuid4(), "code": code, "description": code.replace("_", " ").title()},
            )
    admin_id = bind.execute(sa.text("SELECT id FROM roles WHERE name='Admin / Partner'")).scalar()
    if admin_id:
        bind.execute(
            sa.text("INSERT INTO role_permissions (role_id, permission_id) SELECT :role_id, id FROM permissions ON CONFLICT DO NOTHING"),
            {"role_id": admin_id},
        )
    for role_name, codes in ROLE_PERMISSION_CODES.items():
        role_id = bind.execute(
            sa.text("SELECT id FROM roles WHERE name=:name"), {"name": role_name}
        ).scalar()
        if role_id:
            for code in codes:
                bind.execute(
                    sa.text("INSERT INTO role_permissions (role_id, permission_id) SELECT :role_id, id FROM permissions WHERE code=:code ON CONFLICT DO NOTHING"),
                    {"role_id": role_id, "code": code},
                )


def downgrade() -> None:
    inspector = inspect(op.get_bind())
    op.drop_table("user_roles")
    for foreign_key in inspector.get_foreign_keys("users"):
        if foreign_key["constrained_columns"] in (["created_by_id"], ["updated_by_id"]):
            op.drop_constraint(foreign_key["name"], "users", type_="foreignkey")
    for column in ("updated_by_id", "created_by_id", "is_verified", "mobile"):
        op.drop_column("users", column)
    for column in ("is_active", "is_system_role", "description"):
        op.drop_column("roles", column)
    for constraint in inspector.get_unique_constraints("roles"):
        if constraint["column_names"] == ["code"]:
            op.drop_constraint(constraint["name"], "roles", type_="unique")
    op.drop_column("roles", "code")
