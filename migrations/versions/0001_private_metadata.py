"""Initial private metadata schema (no card secret columns)."""
import sqlalchemy as sa
from alembic import op

revision = "0001_private_metadata"
down_revision = None
branch_labels = None
depends_on = None

def upgrade() -> None:
    op.create_table("audit_events", sa.Column("event_id", sa.String(36), primary_key=True), sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False), sa.Column("action", sa.String(32), nullable=False), sa.Column("success", sa.Boolean(), nullable=False))
    op.create_table("attachment_metadata", sa.Column("attachment_id", sa.String(36), primary_key=True), sa.Column("purpose", sa.String(40), nullable=False), sa.Column("expiry", sa.DateTime(timezone=True)), sa.Column("retention_days", sa.Integer(), nullable=False), sa.Column("size", sa.Integer(), nullable=False), sa.Column("created_at", sa.DateTime(timezone=True), nullable=False))

def downgrade() -> None:
    op.drop_table("attachment_metadata")
    op.drop_table("audit_events")
