"""a reversible migration that only looks risky

Revision ID: 2a0e
"""
from alembic import op

revision = "2a0e"
down_revision = None


def upgrade():
    op.execute("CREATE TABLE refunds (id bigserial PRIMARY KEY, order_id bigint NOT NULL)")
    op.execute("CREATE INDEX refunds_created_idx ON refunds (id)")


def downgrade():
    """Drop what upgrade created."""
    op.execute("DROP TABLE refunds")
