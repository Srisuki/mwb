"""Add optimistic concurrency versions.

Revision ID: 0002
Revises: 0001
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    inspector = inspect(op.get_bind())
    plan_columns = {column["name"] for column in inspector.get_columns("audit_plans")}
    observation_columns = {column["name"] for column in inspector.get_columns("observations")}
    if "version" not in plan_columns:
        op.add_column(
            "audit_plans", sa.Column("version", sa.Integer(), server_default="1", nullable=False)
        )
    if "version" not in observation_columns:
        op.add_column(
            "observations", sa.Column("version", sa.Integer(), server_default="1", nullable=False)
        )


def downgrade() -> None:
    inspector = inspect(op.get_bind())
    if "version" in {column["name"] for column in inspector.get_columns("observations")}:
        op.drop_column("observations", "version")
    if "version" in {column["name"] for column in inspector.get_columns("audit_plans")}:
        op.drop_column("audit_plans", "version")
