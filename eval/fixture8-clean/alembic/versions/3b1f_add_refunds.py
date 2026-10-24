"""add refunds

Revision ID: 3b1f
"""
from alembic import op

revision = "3b1f"
down_revision = "2a0e"


def upgrade():
    op.execute("CREATE INDEX CONCURRENTLY refunds_order_idx ON refunds (order_id)")
    op.execute("ALTER TABLE refunds ADD COLUMN reason text")


def downgrade():
    op.execute("ALTER TABLE refunds DROP COLUMN reason")
    op.execute("DROP INDEX CONCURRENTLY refunds_order_idx")
